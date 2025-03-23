import os

def get_session_files(directory: str):
    if os.listdir(directory) is None or len(os.listdir(directory)) == 0:
        raise FileNotFoundError
    
    return [
        os.path.join(directory, f) for f in os.listdir(directory)
        if f.endswith('.session')
    ]