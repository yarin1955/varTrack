import hashlib
import hmac
import re
from typing import Dict, Any, List, Optional

from flask import jsonify

from app.models.git_platform import GitPlatform
from app.models.role import Role
from app.utils.file_change import ChangeFile
from app.utils.normalized_push import NormalizedPush


class WebhooksHandler:

    @staticmethod
    def handle_webhook(platform: GitPlatform, raw_payload, signature, event_type, secret, role: Role):

        if not WebhooksHandler.verify_signature(secret, raw_payload, signature):
            return jsonify({'error': 'Invalid signature'}), 401

        change_files: List[ChangeFile] = []

        if role.envAsPR and platform.is_pr_event(event_type):
            change_files = platform.normalize_pr_payload(raw_payload)
            return change_files

        if platform.is_push_event(event_type):
            change_files = platform.normalize_push_payload(raw_payload)
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

    @staticmethod
    def handle_pr_event(request):
        pass

    @staticmethod
    def handle_push_event(payload: Dict[str, Any], platform_cls: GitPlatform, role_config: Dict[str, Any]) -> List[Dict[str, Any]]:

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
        role = base_role.resolve_role_for_repo(repo_name)

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
