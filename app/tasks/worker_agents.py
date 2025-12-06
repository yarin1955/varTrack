from app.celery_app import celery as celery_app


@celery_app.task(name='app.worker_agent_task', bind=True)
def worker_agent_task(self):
    """Worker agent that generates a random number"""
    random_number = "7"
    print(f"Worker Agent [{self.request.id}] generated: {random_number}")
    return {
        'task_id': self.request.id,
        'random_number': random_number,
        'agent_type': 'worker'
    }

@celery_app.task(name='app.data_manager', bind=True, queue='worker_agents')
def data_manager(platform, datasource, actionable_items, event_type):
    # 6. Initialize Datasource Connection
    try:
        datasource_instance = DataSourceFactory.create(**datasource_config)
        print(f"Datasource instance: {datasource_instance}")

        ds_adapter = DSAdapterFactory.create(config=datasource_instance)
        ds_adapter.connect()
    except Exception as e:
        print(f"❌ Error initializing datasource: {e}")
        return {'status': 'error', 'message': str(e)}

    processed_count = 0

    # 7. Process Each Actionable Item
    for item in actionable_items:
        destined_file = item.get('file_path')
        repo_name = item.get('repository')
        # Use .get() to avoid KeyError. Fallback to commit_hash if after_sha isn't present.
        after_sha = item.get('after_sha') or item.get('commit_hash')
        before_sha = item.get('before_sha')

        print(f"Processing changes for file: {destined_file}")

        try:
            # Fetch Current Content
            current_file_content = None
            if after_sha:
                current_file_content = asyncio.run(platform_instance.get_file_from_commit(
                    repo_name,
                    after_sha,
                    destined_file
                ))

            # Fetch Previous Content (if exists)
            previous_file_content = None
            if before_sha:
                previous_file_content = asyncio.run(platform_instance.get_file_from_commit(
                    repo_name,
                    before_sha,
                    destined_file
                ))

            # Convert to JSON String (Handling YAML/XML/etc conversion)
            current_obj = "{}"
            if current_file_content:
                current_obj = FileFormatsHandler.convert_string_to_json(current_file_content)

            previous_obj = "{}"
            if previous_file_content:
                previous_obj = FileFormatsHandler.convert_string_to_json(previous_file_content)

            current_section = find_key_iterative(current_obj, "varTrack")
            previous_section = find_key_iterative(previous_obj, "varTrack")

            # Flatten
            current_flattened_data = flatten_dfs(current_section)
            previous_flattened_data = flatten_dfs(previous_section)

            # Compare
            state_comparison = compare_states(current_data=current_flattened_data, old_data=previous_flattened_data)

            datasource_config = current_app.config.get(datasource)
            datasource_instance = DataSourceFactory.create(**datasource_config)
            print(f"Datasource instance: {datasource_instance}")

            ds_adapter = DSAdapterFactory.create(config=datasource_instance)
            ds_adapter.connect()
            cmd= InsertCommand(ds_adapter, state_comparison['changed']['value']['new'])
            invoker.execute_command(cmd)

        except Exception as e:
            print(f"❌ Error processing file {destined_file}: {e}")
            # traceback.print_exc()
            continue

    return {
        'status': 'success',
        'processed_files': processed_count,
        'total_actionable': len(actionable_items)
    }

