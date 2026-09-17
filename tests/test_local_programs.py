import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from media_library import MediaLibrary
from local_programs import ProgramRenderer
from display_activity import DisplayActivity
import display_preview
import program_options
import program_schedule
import settings
import panel_server


def photo(color):
    out=io.BytesIO();Image.new('RGB',(400,300),color).save(out,format='PNG');return out.getvalue()


class Programs(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.library=MediaLibrary(self.root/'media')
        self.programs=ProgramRenderer(self.library,self.root/'cache')
        self.now=datetime(2026,9,17,12,tzinfo=ZoneInfo('America/Edmonton'))
        self.config={'timezone':'America/Edmonton','active_program':'simple-weather','latitude':53.5,'longitude':-113.5,'location_name':'Edmonton'}

    def test_upload_validation_and_delete(self):
        with self.assertRaises(ValueError):self.library.add(b'not an image','bad')
        with self.assertRaises(ValueError):self.library.path('../../config.json')
        item=self.library.add(photo('red'),'../family.png')
        self.assertEqual(len(self.library.list()),1)
        self.assertEqual(self.library.image(item['id']).size,(400,300))
        self.library.delete(item['id']);self.assertEqual(self.library.list(),[])

    def test_slideshow_uses_deliveries_not_previews_and_resumes(self):
        first=self.library.add(photo('red'),'First')['id'];second=self.library.add(photo('blue'),'Second')['id']
        first_body=self.programs.render('photo-frame',self.config,self.now)
        self.assertEqual(display_preview.metadata(first_body)['image_id'],first)
        # Even a far-future preview cannot move a never-delivered slideshow.
        self.assertEqual(display_preview.metadata(self.programs.render('photo-frame',self.config,self.now+timedelta(hours=5)))['image_id'],first)
        self.programs.delivered(first_body,self.now.timestamp())
        self.assertEqual(display_preview.metadata(self.programs.render('photo-frame',self.config,self.now+timedelta(minutes=59)))['image_id'],first)
        second_body=self.programs.render('photo-frame',self.config,self.now+timedelta(hours=1))
        self.assertEqual(display_preview.metadata(second_body)['image_id'],second)
        self.programs.delivered(second_body,(self.now+timedelta(hours=1)).timestamp())
        restored=ProgramRenderer(self.library,self.root/'cache')
        self.assertEqual(display_preview.metadata(restored.render('photo-frame',self.config,self.now+timedelta(minutes=65)))['image_id'],second)
        # An intervening program starts a full photo interval on reactivation.
        self.programs.delivered(self.programs.render('clock-calendar',self.config,self.now),self.now.timestamp())
        self.assertEqual(display_preview.metadata(self.programs.render('photo-frame',self.config,self.now+timedelta(days=1)))['image_id'],second)

    def test_exact_last_fetched_bytes_survive_new_render_and_restart(self):
        activity=DisplayActivity(self.root/'cache'/'events.json')
        old=photo('red');new=photo('blue')
        self.assertEqual(activity.preview(),b'')
        activity.record(3600,'Fixed',body=old)
        self.assertEqual(activity.preview(),old)
        self.assertEqual(DisplayActivity(activity.path).preview(),old)
        activity.record(1800,'Fixed',body=new)
        self.assertEqual(activity.preview(),new)
        self.assertEqual(len(list((self.root/'cache').glob('fetched-*.png'))),1)

    def test_reminder_boundary_and_return(self):
        at=(self.now+timedelta(minutes=20)).timestamp()
        c=dict(self.config,reminders=[{'id':'test','at':at,'minutes':10,'title':'Water plants','message':'Living room','icon':'heart'}])
        self.assertEqual(program_schedule.selected(c,self.now),'simple-weather')
        self.assertEqual(program_schedule.next_boundary(c,self.now),at)
        during=self.now+timedelta(minutes=25)
        self.assertEqual(program_schedule.selected(c,during),'reminder')
        body=self.programs.render('reminder',c,during)
        self.assertEqual(display_preview.metadata(body)['next_update'],at+600)
        self.assertEqual(program_schedule.selected(c,self.now+timedelta(minutes=30)),'simple-weather')
        c.update(program_schedule_enabled=True,program_schedule={'00:00':'photo-frame','12:25':'clock-calendar'})
        self.assertEqual(program_schedule.selected(c,self.now+timedelta(minutes=30)),'clock-calendar')

    def test_countdown_midnight_and_clock_settings(self):
        config=dict(self.config,app_settings={'countdown':{'date':'2026-09-18','title':'A trip'},'clock-calendar':{'format':'24','week_start':'sunday'}})
        program_options.validate(config,self.library)
        body=self.programs.render('countdown',config,self.now.replace(hour=23,minute=50))
        self.assertEqual(display_preview.metadata(body)['next_update'],self.now.replace(day=18,hour=0,minute=0).timestamp())
        self.assertEqual(Image.open(io.BytesIO(self.programs.render('clock-calendar',config,self.now))).size,(600,800))

    def test_daylight_dated_cache_and_missing_data(self):
        body=self.programs.render('daylight',self.config,self.now)
        self.assertEqual(display_preview.metadata(body)['next_update'],self.now.timestamp()+900)
        self.programs.sun={'location':[53.5,-113.5,'America/Edmonton'],'fetched_at':self.now.timestamp(),'daily':{'time':['2026-09-16','2026-09-17'],'sunrise':['2026-09-16T07:10','2026-09-17T07:12'],'sunset':['2026-09-16T19:45','2026-09-17T19:42'],'daylight_duration':[45300,45000]}}
        body=self.programs.render('daylight',self.config,self.now)
        self.assertEqual(display_preview.metadata(body)['next_update'],self.now.timestamp()+3600)
        self.assertEqual(Image.open(io.BytesIO(body)).size,(600,800))

    def test_reminder_validation_and_media_reference_cleanup(self):
        renderer=SimpleNamespace(config=self.config,settings_changed=threading.Event(),library=self.library)
        store=settings.Settings(renderer,self.root/'config.json')
        future=datetime.now(ZoneInfo(self.config['timezone']))+timedelta(days=1)
        payload={'title':'Test','message':'Note','when':future.strftime('%Y-%m-%dT%H:%M'),'minutes':10,'icon':'star'}
        result=store.reminder(payload);self.assertEqual(len(result['reminders']),1)
        with self.assertRaisesRegex(ValueError,'overlaps'):store.reminder(payload)
        with self.assertRaises(ValueError):program_options.reminder_at('2026-03-08T02:30','America/Edmonton')
        ident=self.library.add(photo('white'),'Event')['id']
        renderer.config['app_settings']={'countdown':{'image':ident}}
        store.delete_picture(ident)
        self.assertEqual(store.snapshot()['app_settings']['countdown']['image'],'')
        store.reminder({'action':'delete','id':result['reminders'][0]['id']})
        self.assertEqual(store.snapshot()['reminders'],[])

    def test_return_fetch_uses_current_weather_page_without_network_weather_call(self):
        config=dict(self.config,renderer_url='http://renderer',enabled_pages=['daily'],page_schedule={'00:00':'daily'},advisories=False)
        old=photo('white');new=photo('black')
        with patch.object(panel_server.urllib.request,'urlopen',return_value=io.BytesIO(old)):
            renderer=panel_server.RenderedPages(config,self.root/'mirror')
        renderer.config=dict(config,active_program='weather-cal')
        with patch.object(renderer.weather,'fetch',side_effect=AssertionError('No weather API in device fetch')), patch.object(panel_server.urllib.request,'urlopen',return_value=io.BytesIO(new)) as request:
            self.assertEqual(renderer.for_fetch(),new)
            self.assertEqual(renderer.page,'daily')
            self.assertEqual(request.call_args.kwargs['timeout'],3)

    def test_photo_timer_and_reminder_cap_in_real_image_handler(self):
        image=self.library.add(photo('red'),'First')
        renderer=SimpleNamespace(config=dict(self.config,active_program='photo-frame'),activity=Mock(),programs=self.programs)
        renderer.current=lambda:self.programs.render('photo-frame',renderer.config,datetime.now(ZoneInfo(self.config['timezone'])))
        handler=object.__new__(panel_server.make_handler(renderer));handler.path='/panel.png';handler.headers={'User-Agent':'NookPanel/0.3'};handler.wfile=io.BytesIO();handler.send_response=Mock();handler.send_header=Mock();handler.end_headers=Mock()
        renderer.config['reminders']=[{'at':datetime.now().timestamp()+300,'minutes':10}]
        handler.do_GET()
        sent=dict(c.args for c in handler.send_header.call_args_list)
        self.assertTrue(295<=int(sent['X-Nook-Refresh-Seconds'])<=300)
        self.assertEqual(renderer.activity.record.call_args.kwargs['body'],handler.wfile.getvalue())

class APIIntegration(unittest.TestCase):
    def test_upload_preview_delete_and_last_fetch_http(self):
        from http.server import ThreadingHTTPServer
        from urllib.request import Request,urlopen
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);library=MediaLibrary(root/'media')
            config={'timezone':'America/Edmonton','active_program':'simple-weather','renderer_url':'http://renderer'}
            activity=DisplayActivity(root/'cache'/'events.json');old=photo('red');candidate=photo('blue')
            activity.record(3600,'Fixed',body=old)
            renderer=SimpleNamespace(config=config,library=library,activity=activity,current=lambda:candidate,settings_changed=threading.Event())
            store=settings.Settings(renderer,root/'config.json')
            http=ThreadingHTTPServer(('127.0.0.1',0),settings.make_handler(store))
            thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(http.server_port)
            try:
                with urlopen(base+'/api/display/preview.png') as response:self.assertEqual(response.read(),old)
                with urlopen(Request(base+'/api/media',data=candidate,headers={'Content-Type':'image/png','X-File-Name':'Test%20art.png'})) as response:item=json.load(response)['picture']
                self.assertEqual(item['name'],'Test art.png')
                with urlopen(base+'/api/program/preview.png?program=photo-frame&image='+item['id']) as response:
                    self.assertEqual(Image.open(io.BytesIO(response.read())).size,(600,800))
                with urlopen(base+'/dashboard.js') as response:self.assertIn(b'renderCustomFields',response.read())
                with urlopen(Request(base+'/api/media/delete',data=json.dumps({'id':item['id']}).encode(),headers={'Content-Type':'application/json'})) as response:
                    self.assertEqual(json.load(response)['pictures'],[])
                self.assertEqual(len(activity.events),1)
            finally:
                http.shutdown();http.server_close();thread.join()
