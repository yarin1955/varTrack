import hashlib
import hmac

from app.models.git_platform import GitPlatform
from app.utils.normalized_push import NormalizedPush


class WebhooksHandler:

    # @staticmethod
    # def handle_webhook(platform, datasource, raw_payload, signature, event_type):
        # secret = (current_app.config.get(platform))["secret"]
        # if not WebhooksHandler.verify_signature(secret, raw_payload, signature):
        #     return jsonify({'error': 'Invalid signature'}), 401
        #
        # if WebhooksHandler.is_push_event(event_type):
        #     commits = WebhooksHandler.handle_push_event(raw_payload)
        #
        # elif WebhooksHandler.is_pr_event(event_type):
        #     commits = WebhooksHandler.handle_pr_event(raw_payload)
        #
        # platform_instance= PlatformFactory.create(**current_app.config.get(platform))
        #
        # platform_instance.auth()
        #
        # new_file= platform_instance.get_file_from_commit()
        #
        # dsadapter_instance= DSAdapterFactory.create()
        #
        # validator = SchemaValidator(schema_dir="./schemas")
        #
        # # Validate single file
        # # result = validator.validate_file("data/user_data.json")
        #
        #
        #
        # # invoker = CommandInvoker()
        # #
        # # print("=== Filesystem Commands ===")
        # # invoker.execute_command(UpdateFileCommand(fs, "readme.txt", "Hello World"))
        # # invoker.execute_command(UpdateFileCommand(fs, "readme.txt", "Hello World"))
        #
        # # redis_client = redis.Redis(host='localhost', port=6379, decode_responses=False)
        # # redis_strategy = RedisAdapter(redis_client)
        # #
        # # # Create invoker
        # # invoker = StorageInvoker()
        # #
        # # # Create and execute commands
        # # insert_cmd = InsertCommand(redis_strategy, "user:1", "John Doe")
        # # invoker.execute_command(insert_cmd)





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

    @staticmethod
    def handle_pr_event(request):
        pass

    @staticmethod
    def handle_push_event(request, cls: GitPlatform, file):
        normalized_push :NormalizedPush= cls.normalize_push_payload(request, file)

        first_commit= normalized_push.commits[0].hash
        last_commit= normalized_push.commits[-1].hash

        print(f"first: {first_commit}; last: {last_commit}")

        # if len(normalized_push.commits) == 1:
        #     return {"first": first_commit, "last": None}

        return {"first": first_commit, "last": last_commit}





    # @staticmethod
    # def handle_push_event(data):
    #     """Handle push events"""
    #     ref = data.get('ref', 'unknown')
    #     repository = data.get('repository', {}).get('full_name', 'unknown')
    #     pusher = data.get('pusher', {}).get('name', 'unknown')
    #
    #     print(f"🚀 PUSH EVENT")
    #     print(f"   Repository: {repository}")
    #     print(f"   Branch: {ref}")
    #     print(f"   Pusher: {pusher}")
    #
    #     commits = data.get('commits', [])
    #     WebhooksHandler.print_file_changes(commits, 'push')

    @staticmethod
    def is_push_event(event_type):
        return event_type == 'push'

    @staticmethod
    def is_pr_event(event_type):
        return event_type == 'pull_request'

    @staticmethod
    def check_file_changed(webhook_payload, filename):
        head_commit = webhook_payload.get('head_commit', {})

        # Combine all three arrays and check if file is present
        all_changed_files = (
                head_commit.get('added', []) +
                head_commit.get('removed', []) +
                head_commit.get('modified', [])
        )

        return filename in all_changed_files
