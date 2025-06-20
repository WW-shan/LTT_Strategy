import os

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
