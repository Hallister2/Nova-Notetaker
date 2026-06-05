from app.core.settings import ensure_user_data_dirs
from app.ui.main_window import run_app


if __name__ == "__main__":
    ensure_user_data_dirs()
    run_app()
