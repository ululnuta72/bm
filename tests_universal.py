import json
import os
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from universal import check, story_text
from generate_job import ask_model, load_config
from PIL import Image
from tinyvideo import landscape_frame

class UniversalJobTest(unittest.TestCase):
    def test_openai_compatible_request(self):
        result = BytesIO(b'{"choices":[{"message":{"content":"{\\"ok\\":true}"}}]}')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'OPENAI_BASE_URL': 'https://api.example/v1/', 'OPENAI_MODEL': 'test-model'}), patch('urllib.request.urlopen', return_value=result) as send:
            self.assertEqual(ask_model([{'role': 'system', 'content': 'Return JSON'}, {'role': 'user', 'content': 'test'}], {'type': 'object'}, 123), {'ok': True})
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.example/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
        payload = json.loads(request.data)
        self.assertEqual(payload['model'], 'test-model')
        self.assertEqual(payload['max_tokens'], 123)
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertIn('Return JSON matching this schema exactly', payload['messages'][0]['content'])

    def test_scheduled_config(self):
        config = load_config('config/scheduled-job.json')
        self.assertEqual(config['niche'], 'BABY BITES US')
        self.assertEqual(config['format'], 'shorts')
        self.assertEqual(config['target_duration_seconds'], 30)
        self.assertEqual(len(config['cast']), 2)

    def test_target_duration(self):
        job = json.loads(Path('examples/universal-job.json').read_text())
        job['target_duration_seconds'] = 30
        self.assertEqual(check(job)['target_duration_seconds'], 30)
        for duration in (0, 601, True):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                check({**job, 'target_duration_seconds': duration})

    def test_contract(self):
        job = json.loads(Path('examples/universal-job.json').read_text())
        check(job)
        story = story_text(job)
        self.assertIn('language: en', story)
        self.assertIn('Mika: The ocean', story)
        job['lines'][0]['text'] = 'bad | injected field'
        with self.assertRaises(ValueError):
            check(job)

    def test_javanese_job(self):
        job = json.loads(Path('examples/wedang-jahe-jawa.json').read_text())
        check(job)
        self.assertIn('language: jv', story_text(job))

    def test_uk_job(self):
        job = json.loads(Path('examples/baby-first-tastes-uk.json').read_text())
        check(job)
        self.assertIn('language: en-GB', story_text(job))

    def test_landscape_layout(self):
        frame = Image.new('RGB', (1080, 1920))
        layout = landscape_frame(frame, {'title': 'Test', 'brand': 'NUSANTARA'}, [], 0)
        self.assertEqual(layout.size, (1920, 1080))

if __name__ == '__main__':
    unittest.main()
