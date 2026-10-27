from app.database import migrate_project_metadata_schema


def main() -> None:
    migrate_project_metadata_schema()
    print(
        "Project metadata migration completed. Existing scan, account, and "
        "model records were preserved."
    )


if __name__ == "__main__":
    main()
