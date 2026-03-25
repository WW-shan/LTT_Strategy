import errno
import os
import shutil


def ensure_dir_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def ensure_file_exists(file_path):
    if not os.path.exists(file_path):
        parent_dir = os.path.dirname(file_path)
        if parent_dir:
            ensure_dir_exists(parent_dir)
        with open(file_path, 'w', encoding='utf-8') as f:
            if file_path.endswith('.json'):
                f.write('{}')
            else:
                f.write('')


def move_path_if_missing(source_path, target_path):
    if not os.path.exists(source_path) or os.path.exists(target_path):
        return False

    target_parent = os.path.dirname(target_path)
    if target_parent:
        ensure_dir_exists(target_parent)

    try:
        os.replace(source_path, target_path)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise

        shutil.copy2(source_path, target_path)
        os.remove(source_path)

    return True


def migrate_tmp_state_files(legacy_tmp_dir, tmp_dir):
    if not os.path.isdir(legacy_tmp_dir):
        return

    ensure_dir_exists(tmp_dir)

    for entry in os.listdir(legacy_tmp_dir):
        if entry.startswith('last_can_biao_xiu_state_'):
            move_path_if_missing(
                os.path.join(legacy_tmp_dir, entry),
                os.path.join(tmp_dir, entry),
            )


def prepare_runtime_state(
    data_dir,
    tmp_dir,
    allowed_users_file,
    user_settings_file,
    log_file,
    legacy_base_dir,
):
    ensure_dir_exists(data_dir)
    ensure_dir_exists(tmp_dir)

    move_path_if_missing(os.path.join(legacy_base_dir, 'allowed_users.txt'), allowed_users_file)
    move_path_if_missing(os.path.join(legacy_base_dir, 'user_settings.json'), user_settings_file)
    move_path_if_missing(os.path.join(legacy_base_dir, 'strategy.log'), log_file)
    migrate_tmp_state_files(os.path.join(legacy_base_dir, 'tmp'), tmp_dir)

    ensure_file_exists(allowed_users_file)
    ensure_file_exists(user_settings_file)
