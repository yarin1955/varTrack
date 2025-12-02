import hashlib
import hmac
import re
from typing import Dict, Any, List, Optional

from app.models.git_platform import GitPlatform
from app.models.role import Role
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
    def handle_push_event(payload: Dict[str, Any], platform_cls: GitPlatform, role_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Handle push event with Role-based filtering.

        Args:
            payload: The JSON payload from the webhook
            platform_cls: The GitPlatform class used for normalization
            role_config: The raw dictionary configuration for the Role

        Returns:
            List of dictionaries containing 'commit', 'file', 'env', and 'key' for valid changes.
        """
        # 1. Normalize payload (get all commits)
        normalized_push: NormalizedPush = platform_cls.normalize_push_payload(payload, file=None)

        # 2. Resolve Role configuration
        try:
            # Instantiate Role to validate and use helper methods
            base_role = Role(**role_config)
        except Exception as e:
            print(f"❌ Role Configuration Error: {e}")
            return []

        # Apply overrides based on repository name
        repo_name = normalized_push.repository
        role = base_role.get_effective_config(repo_name)

        print(f"Processing Push for Repo: {repo_name} with Role strategy")

        results = []

        # 3. Iterate commits and filter based on Role strategy
        for commit in normalized_push.commits:
            # Combine all changes
            changed_files = set(commit.added + commit.modified)

            for file_path in changed_files:
                match_context = WebhooksHandler._match_file_to_role(file_path, normalized_push.ref, role)

                if match_context:
                    print(f"   -> Match found: {file_path} (Env: {match_context.get('env')})")
                    results.append({
                        "commit_hash": commit.hash,
                        "file_path": file_path,
                        "repository": repo_name,
                        "env": match_context.get('env'),
                        "key": match_context.get('key'),
                        "variables": match_context.get('variables', {}),
                        # Add before/after SHAs for the whole push event to allow diffing
                        "before_sha": normalized_push.before,
                        "after_sha": normalized_push.after
                    })

        return results

    @staticmethod
    def _match_file_to_role(file_path: str, ref: str, role: Role) -> Optional[Dict[str, Any]]:
        """
        Check if a file matches the Role's file strategy (fileName or filePathMap)
        and derive environment variables.
        """
        env = None
        variables = {}

        # Strategy A: Specific FileName
        if role.fileName:
            if file_path == role.fileName:
                # Determine Env
                if role.envAsBranch:
                    # Strip 'refs/heads/' if present
                    env = ref.replace('refs/heads/', '')
                elif role.branchMap:
                    # Check if current branch matches any regex in branchMap
                    branch_name = ref.replace('refs/heads/', '')
                    for pattern, env_name in role.branchMap.items():
                        if re.match(pattern, branch_name):
                            env = env_name
                            break
                # If neither, env might be None or rely on external default (not handled here)

        # Strategy B: File Path Map (Directory/Regex strategy)
        elif role.filePathMap:
            for pattern, val in role.filePathMap.items():
                match = re.match(pattern, file_path)
                if match:
                    # Extract variables from named groups
                    variables.update(match.groupdict())

                    # If the value in map is just a placeholder like "{env}", try to resolve it
                    # OR if the value is a literal environment name
                    if '{' not in val:
                        env = val
                    else:
                        # Try to format the value string using captured groups
                        try:
                            env = val.format(**variables)
                        except KeyError:
                            pass

                    # If 'env' was captured in regex group but not explicitly mapped
                    if not env and 'env' in variables:
                        env = variables['env']

                    break

        if env:
            variables['env'] = env
            variables['repoName'] = role.repositories[0] if role.repositories else "unknown" # simplified
            # Generate Unique Key
            try:
                # Provide default vars for key generation
                fmt_vars = {
                    "repoName": variables.get('repoName', ''),
                    "env": env,
                    "branch": ref.replace('refs/heads/', ''),
                    "file_path": file_path
                }
                fmt_vars.update(variables)

                key = role.uniqueKeyName.format(**fmt_vars)

                return {
                    "env": env,
                    "key": key,
                    "variables": variables
                }
            except KeyError as e:
                print(f"⚠️ Could not generate uniqueKey: Missing variable {e}")
                return None

        return None

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
