import sys
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import program_options as options
import program_schedule

class Repeats(unittest.TestCase):
    def reminder(self,when,repeat='daily',minutes=15,zone='America/New_York'):
        return {'id':'r','at':options.reminder_at(when,zone),'when':when,'repeat':repeat,'minutes':minutes,'title':'Routine','message':'','icon':'star'}

    def test_daily_keeps_wall_time_across_dst_and_renderer_gets_occurrence(self):
        zone=ZoneInfo('America/New_York');r=self.reminder('2026-03-07T08:00')
        now=datetime(2026,3,8,7,55,tzinfo=zone);c={'timezone':str(zone),'reminders':[r],'active_program':'countdown'}
        self.assertEqual(program_schedule.next_boundary(c,now),(now+timedelta(minutes=5)).timestamp())
        occurrence=options.active_reminder(c,now.replace(hour=8,minute=5))
        self.assertEqual(datetime.fromtimestamp(occurrence['at'],zone).hour,8)
        self.assertEqual(occurrence['at']-r['at'],23*3600)
        self.assertEqual(program_schedule.selected(c,now.replace(hour=8,minute=15)),'countdown')

    def test_weekdays_skip_weekend_and_weekly_uses_anchor_day(self):
        zone=ZoneInfo('America/New_York');now=datetime(2026,9,18,12,tzinfo=zone)
        r=self.reminder('2026-09-18T09:00','weekdays');view=options.reminder_view(r,str(zone),now.timestamp())
        self.assertEqual(datetime.fromtimestamp(view['occurrence_at'],zone).strftime('%Y-%m-%d %H:%M'),'2026-09-21 09:00')
        r['repeat']='weekly';view=options.reminder_view(r,str(zone),now.timestamp())
        self.assertEqual(datetime.fromtimestamp(view['occurrence_at'],zone).strftime('%Y-%m-%d'),'2026-09-25')

    def test_missing_time_skipped_and_repeated_hour_runs_once(self):
        zone=ZoneInfo('America/New_York');r=self.reminder('2026-03-07T02:30')
        start=datetime(2026,3,8,0,tzinfo=zone).timestamp()
        rows=options.occurrences(r,str(zone),start,start+48*3600)
        self.assertEqual(datetime.fromtimestamp(rows[0]['at'],zone).strftime('%Y-%m-%d'),'2026-03-09')
        r=self.reminder('2026-10-31T01:30');start=datetime(2026,11,1,0,tzinfo=zone).timestamp()
        rows=options.occurrences(r,str(zone),start,start+25*3600)
        self.assertEqual(len(rows),1)
        self.assertEqual(datetime.fromtimestamp(rows[0]['at'],zone).fold,0)

    def test_cross_midnight_active_and_repeat_conflict(self):
        zone=ZoneInfo('America/New_York');r=self.reminder('2026-09-18T23:55',minutes=15)
        now=datetime(2026,9,20,0,3,tzinfo=zone)
        self.assertIsNotNone(options.active_reminder({'timezone':str(zone),'reminders':[r]},now))
        other=self.reminder('2026-09-21T00:00','weekly')
        self.assertTrue(options.reminders_overlap(r,other,str(zone)))
        other=self.reminder('2026-09-21T01:00','weekly')
        self.assertFalse(options.reminders_overlap(r,other,str(zone)))

    def test_legacy_one_shot_and_future_series(self):
        zone=ZoneInfo('America/New_York');r=self.reminder('2027-03-06T09:00','weekdays')
        now=datetime(2026,9,18,12,tzinfo=zone)
        view=options.reminder_view(r,str(zone),now.timestamp())
        self.assertEqual(datetime.fromtimestamp(view['occurrence_at'],zone).strftime('%Y-%m-%d'),'2027-03-08')
        r=self.reminder('2026-09-17T08:00');r.pop('repeat')
        self.assertIsNone(options.reminder_view(r,str(zone),now.timestamp())['occurrence_at'])
