"""Platform-specific private application and OAuth storage locations."""
import os
from pathlib import Path


def data_dir():
    if os.name=='nt':return Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local'))) / 'MediaDesk'
    return Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share'))) / 'mediadesk'


def google_config_dir():
    default=data_dir()/'google' if os.name=='nt' else Path.home()/'.config/youtube-readonly'
    return Path(os.environ.get('MEDIADESK_GOOGLE_CONFIG',str(default)))
