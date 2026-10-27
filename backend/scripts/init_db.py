from app.database import initialize_missing_tables


def main() -> None:
    created_tables = initialize_missing_tables()
    if created_tables:
        print("Created missing tables: " + ", ".join(created_tables))
    else:
        print("All required tables already exist; no schema changes were made.")


if __name__ == "__main__":
    main()
