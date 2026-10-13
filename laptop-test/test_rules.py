import json
from pathlib import Path
import unittest
from fall_detector import FallDetector, Observation


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.detector = FallDetector(json.loads((Path(__file__).parent / 'config.json').read_text())["fall"])

    def feed(self, t, y=200, angle=0):
        return self.detector.update(Observation(t,y,300,angle),t)

    def test_lying_at_start_does_not_alert(self):
        for i in range(30):
            state,event = self.feed(i*0.1,350,80)
            self.assertIsNone(event)
        self.assertEqual(state,'NORMAL')

    def test_transition_and_persistence_alert_once(self):
        self.feed(0)
        self.feed(0.1)
        self.feed(0.2,330,80)
        events = []
        for i in range(3,25):
            state,event = self.feed(i*0.1,330,80)
            if event: events.append(event)
        self.assertEqual(len(events),1)
        self.assertEqual(state,'POST_FALL')

    def test_tracking_loss_breaks_candidate(self):
        self.feed(0)
        self.feed(0.1,330,80)
        state,event = self.detector.update(None,0.2)
        self.assertEqual(state,'UNKNOWN')
        for i in range(3,25):
            self.assertIsNone(self.feed(i*0.1,330,80)[1])

    def test_sitting_upright_does_not_alert(self):
        self.feed(0)
        for i in range(1,25):
            self.assertIsNone(self.feed(i*0.1,330,10)[1])

    def test_long_gap_cannot_form_transition(self):
        self.feed(0)
        state,event = self.feed(2,330,80)
        self.assertEqual(state,'NORMAL')
        self.assertIsNone(event)

    def test_short_horizontal_transition_recovers_without_alert(self):
        self.feed(0)
        self.feed(0.1,330,80)
        self.feed(0.2,330,80)
        state,event = self.feed(0.3,200,0)
        self.assertEqual(state,'NORMAL')
        self.assertIsNone(event)
        self.assertIsNone(self.detector.candidate)

    def test_acknowledgement_clears_latch(self):
        self.feed(0)
        self.feed(0.1,330,80)
        for i in range(2,20):
            self.feed(i*0.1,330,80)
        self.assertTrue(self.detector.latched)
        self.detector.reset()
        self.assertFalse(self.detector.latched)
        self.assertEqual(self.detector.state,'UNKNOWN')
        self.assertIsNone(self.feed(2,330,80)[1])


if __name__ == '__main__':
    unittest.main()
