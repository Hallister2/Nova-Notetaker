from app.core.settings import ensure_user_data_dirs
from app.core.crash_logging import install_crash_logging
from app.ui.main_window import run_app


if __name__ == "__main__":
    ensure_user_data_dirs()
    install_crash_logging()
    run_app()
