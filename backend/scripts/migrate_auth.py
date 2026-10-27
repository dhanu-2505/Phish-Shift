from app.database import migrate_auth_schema


def main() -> None:
    migrate_auth_schema()
    print(
        "Authentication tables and nullable scan ownership migration completed. "
        "Existing unowned scans remain unassigned."
    )


if __name__ == "__main__":
    main()
