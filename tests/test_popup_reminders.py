import io
import sys
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from local_programs import ProgramRenderer
from media_library import MediaLibrary
import display_preview
from panel_server import RenderedPages
from unittest.mock import patch

class PopupTests(unittest.TestCase):
    def test_delivered_popup_is_not_repeated_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            renderer=ProgramRenderer(MediaLibrary(Path(folder)/'media'),folder)
            now=datetime(2026,9,17,12,tzinfo=ZoneInfo('America/Edmonton'))
            reminder={'id':'r','at':now.timestamp(),'minutes':15,'title':'A reminder','message':'Hello','icon':'star','repeat':'daily'}
            config={'timezone':'America/Edmonton','reminders':[reminder]}
            body=renderer.render('clock-calendar',config,now)
            popup=renderer.overlay_reminder(body,renderer.pending_reminder(config,now))
            self.assertEqual(display_preview.metadata(popup)['reminder_at'],now.timestamp())
            self.assertEqual(display_preview.metadata(popup)['next_update'],now.timestamp()+900)
            self.assertIsNotNone(renderer.pending_reminder(config,now)) # Preview isn't delivery.
            pages=object.__new__(RenderedPages);pages.config=dict(config,active_program='clock-calendar');pages.programs=renderer
            with patch('panel_server.datetime') as clock:
                clock.now.return_value=now
                self.assertEqual(display_preview.metadata(pages.for_fetch())['program'],'reminder')
            renderer.delivered(popup,now.timestamp())
            self.assertIsNone(renderer.pending_reminder(config,now))
            with patch('panel_server.datetime') as clock:
                clock.now.return_value=now
                self.assertEqual(display_preview.metadata(pages.for_fetch())['program'],'clock-calendar')
            restored=ProgramRenderer(renderer.library,folder)
            self.assertIsNone(restored.pending_reminder(config,now))
            self.assertIsNotNone(restored.pending_reminder(config,now+timedelta(days=1)))
            self.assertEqual(Image.open(io.BytesIO(body)).size,Image.open(io.BytesIO(popup)).size)

    def test_countdown_banner_and_weather(self):
        with tempfile.TemporaryDirectory() as folder:
            renderer=ProgramRenderer(MediaLibrary(Path(folder)/'media'),folder)
            now=datetime(2026,9,17,12,tzinfo=ZoneInfo('America/Edmonton'))
            renderer.temperature={'value':16.5,'at':now.timestamp()}
            body=renderer.render('countdown',{'app_settings':{'countdown':{'date':'2026-10-01'}}},now)
            image=Image.open(io.BytesIO(body))
            self.assertEqual(image.getpixel((0,0)),0)
            self.assertEqual(image.getpixel((0,799)),255)
