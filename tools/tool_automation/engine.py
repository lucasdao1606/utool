"""Logic xu ly backend tu dong hoa."""
def get_service_status():
    return {
        "webhook_receiver": "Active 🟢",
        "cron_sync": "Running (Next run in 25m) 🟡",
        "cloud_sync": "Idle ⚪"
    }
