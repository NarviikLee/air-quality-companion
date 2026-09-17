import unittest
from unittest.mock import Mock
from repeated_error_log import RepeatedErrorLog


class RepeatedLogTests(unittest.TestCase):
    def setUp(self):
        self.logger = Mock()
        self.clock = Mock(return_value=0)
        self.log = RepeatedErrorLog(self.logger, clock=self.clock)

    def test_first_immediate_then_minute_summary(self):
        for now in range(0, 61, 4):
            self.clock.return_value = now
            self.log.failure(ValueError('same error'))
        self.assertEqual(self.logger.warning.call_count, 2)
        self.assertEqual(self.logger.warning.call_args[0][-2:], (15, 16))

    def test_error_change_flushes_previous_and_logs_new(self):
        self.log.failure(ValueError('port A'))
        self.log.failure(ValueError('port A'))
        self.log.failure(ValueError('port B'))
        self.assertEqual(self.logger.warning.call_count, 3)
        self.assertEqual(self.logger.warning.call_args[0][-1], 'ValueError: port B')

    def test_error_type_is_part_of_identity(self):
        self.log.failure(ValueError('same'))
        self.log.failure(RuntimeError('same'))
        self.assertEqual(self.logger.warning.call_count, 2)

    def test_recovery_immediate_once_and_resets_failure(self):
        for _ in range(5):
            self.log.failure(ValueError('timeout'))
        self.log.recovered()
        self.log.recovered()
        self.logger.info.assert_called_once()
        self.assertEqual(self.logger.info.call_args[0][1:3], (5, 4))
        self.log.failure(ValueError('timeout'))
        self.assertEqual(self.logger.warning.call_count, 2)

    def test_shutdown_flushes_once(self):
        self.log.failure(ValueError('timeout'))
        self.log.failure(ValueError('timeout'))
        self.log.flush('worker stopping')
        self.log.flush('worker stopping')
        self.assertEqual(self.logger.warning.call_count, 2)

    def test_minute_windows_do_not_double_count(self):
        for now in (0, 30, 60, 90, 120):
            self.clock.return_value = now
            self.log.failure(ValueError('timeout'))
        calls = self.logger.warning.call_args_list
        self.assertEqual(calls[1][0][-2:], (2, 3))
        self.assertEqual(calls[2][0][-2:], (2, 5))

    def test_worker_still_emits_every_failure(self):
        from sensor_worker import SensorWorker
        from sensor_data import PortUnavailableError, SENSORS
        class Source:
            calls = 0
            def read(self):
                self.calls += 1
                if self.calls <= 20:
                    raise PortUnavailableError('none')
                return {s.name: s.initial for s in SENSORS}, None
        source = Source()
        worker = SensorWorker(lambda: source)
        worker.error_log = self.log
        failed, received = [], []
        worker.failed.connect(lambda state, detail: failed.append((state, detail)))
        worker.received.connect(lambda values, main: received.append(values))
        for _ in range(21):
            worker.read()
        self.assertEqual(len(failed), 20)
        self.assertEqual(len(received), 1)
        self.logger.warning.assert_called_once()
        self.logger.info.assert_called_once()


if __name__ == '__main__':
    unittest.main()
