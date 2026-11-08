import unittest

from scripts.inspect_tse_logs import inspect_member


class LogInspectionTests(unittest.TestCase):
    def test_mixed_rounds_and_manual_requests_remain_separate(self) -> None:
        lines = [
            "04/10/2026 08:00:00\tINFO\t1234\tVOTA\tO voto do eleitor foi computado\ta\n",
            "25/10/2026 07:59:00\tINFO\t1234\tVOTA\tSolicitação de dado pessoal do eleitor para habilitação manual\tb\n",
            "25/10/2026 08:00:00\tINFO\t1234\tVOTA\tEleitor foi habilitado\tc\n",
            "25/10/2026 08:01:00\tINFO\t1234\tVOTA\tO voto do eleitor foi computado\td\n",
            "25/10/2026 08:02:00\tINFO\t1234\tOTHER\tO voto do eleitor foi computado\te\n",
            "broken\n",
            "invalid\tINFO\t1234\tVOTA\tmessage\tf\n",
        ]
        result = inspect_member(lines)
        self.assertEqual(result["completion_messages_by_date"], {"2026-10-04": 1, "2026-10-25": 1})
        self.assertEqual(result["manual_request_messages_by_date"], {"2026-10-25": 1})
        self.assertEqual(result["malformed_lines"], 2)
        self.assertEqual(
            result["last_completion_in_file_order_device_time"]["2026-10-25"], "25/10/2026 08:01:00"
        )


if __name__ == "__main__":
    unittest.main()
