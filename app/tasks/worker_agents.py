import json
from datetime import datetime
from pydantic import ValidationError

from app.celery_app import celery as celery_app
from app.models.rule import Rule
from app.pipeline.sources.git_source import GitSource
from app.utils.normalized_pr import NormalizedPR
from app.utils.normalized_push import NormalizedPush


@celery_app.task(name='app.data_manager', bind=True, queue='worker_agents')
def data_manager(self, platform_config: dict, datasource_config: dict, normalize_git_webhook: dict, rule_dict: dict):

    git_event_type = normalize_git_webhook.pop('_type')
    commit_sha = None
    before_sha = None
    git_event= None

    if git_event_type == 'NormalizedPR':
        git_event = NormalizedPR(**normalize_git_webhook)
        before_sha = normalize_git_webhook.get('base_sha')
        commit_sha = normalize_git_webhook.get('head_sha')
    else:
        git_event = NormalizedPush(**normalize_git_webhook)
        before_sha = normalize_git_webhook.get('before')
        commit_sha = normalize_git_webhook.get('after')

    rule = Rule(**rule_dict)

    target_files= git_event.get_matching_files(filename=rule.fileName, file_path_map=rule.filePathMap)

    platform_instance = PlatformFactory.create(**platform_config)

    source = GitSource(
        platform=platform_instance,
        repo_name=repo_name,
        files_to_process=target_files,
        before_sha=before_sha
    )

    parser = ContentParser()
    flattener = Flattenizer(root_key="varTrack")
    differ = DiffExploder()

    sink = MongoSink(
        collection=raw_collection,
        is_upsert_enable=getattr(datasource_instance, 'is_upsert_enable', False),
        batch_size=1000
    )

    processed_files = 0
    total_rows_written = 0

    for file in target_files:
        try:
            # B. TRANSFORMS: Chain of Responsibility

            # 1. Parse (String -> Dict)
            curr_dict = parser.process(file['current'])
            prev_dict = parser.process(file['previous'])

            # 2. Flatten (Dict -> Flat Dict)
            curr_flat = flattener.process(curr_dict)
            prev_flat = flattener.process(prev_dict)

            # 3. Diff (States -> Row Stream)
            rows = differ.process(
                current=curr_flat,
                previous=prev_flat,
                metadata=file['metadata']
            )

            # C. SINK: Write to Buffer
            for row in rows:
                sink.write(row)
                total_rows_written += 1

            processed_files += 1

        except Exception as e:
            print(f"⚠️ [Engine] Skipped file {file['file_path']}: {e}")

    sink.flush()


    return {
        'status': 'success',
        'processed_files': processed_files,
        'config_strategy': role.fileName or "Map"
    }