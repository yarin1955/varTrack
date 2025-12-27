import hashlib
import hmac
import re
from sys import platform
from typing import Dict, Any, List, Optional

from app.models.git_platform import GitPlatform
from app.models.rule import Rule
from app.pipeline.source import Source
from app.utils.file_change import ChangeFile
from app.utils.normalized_push import NormalizedPush


class WebhooksHandler:

    @staticmethod
    def handle_webhook(source: Source ,raw_payload, json_payload, headers, rule: Rule):

        platform= source.settings
        event_type_header = platform.event_type_header

        event_type = headers.get(event_type_header)

        change_files: List[ChangeFile] = []
        if rule["envAsPR"] and platform.is_pr_event(event_type):
            change_files = source.normalize_pr_payload(json_payload)
            return change_files

        if platform.is_push_event(event_type):
            change_files = source.normalize_push_payload(json_payload)
            return change_files

    @staticmethod
    def verify_signature(secret, payload_body, signature_header):
        """Verify webhook signature if secret is configured."""
        if not secret:
            print("ℹ️ No webhook secret configured - skipping signature verification")
            return True  # Skip verification if no secret is set

        if signature_header is None:
            return False

        try:
            sha_name, signature = signature_header.split('=')
            if sha_name != 'sha256':
                return False

            # Create HMAC signature
            mac = hmac.new(secret.encode(), payload_body, hashlib.sha256)
            expected_signature = mac.hexdigest()

            is_valid = hmac.compare_digest(expected_signature, signature)
            if is_valid:
                print("✅ Webhook signature verified")
            else:
                print("❌ Webhook signature verification failed")
            return is_valid

        except ValueError as e:
            print(f"❌ Error parsing signature header: {e}")
            return False

