import psycopg2
import random
import os
import time
from faker import Faker

# Initialize the Faker library to generate mock data
fake = Faker()


def get_db_connection():
    """
    Establishes a connection to the PostgreSQL database.
    Reads connection details from environment variables with sensible defaults.
    """
    # Get connection details from environment variables
    # Default to 'localhost' if running script on the host machine
    db_host = os.getenv('POSTGRES_HOST', 'localhost')
    db_name = os.getenv('POSTGRES_DB', 'bankdb')
    db_user = os.getenv('POSTGRES_USER', 'user')
    db_pass = os.getenv('POSTGRES_PASSWORD', 'password')

    conn_string = f"host='{db_host}' dbname='{db_name}' user='{db_user}' password='{db_pass}' port='5432'"

    # Add retry logic in case the DB isn't fully up yet
    retries = 5
    while retries > 0:
        try:
            conn = psycopg2.connect(conn_string)
            print("Successfully connected to PostgreSQL.")
            return conn
        except psycopg2.OperationalError as e:
            print(f"Connection failed: {e}. Retrying in 5 seconds...")
            retries -= 1
            time.sleep(5)

    print("Could not connect to the database after several attempts.")
    return None


def create_and_populate_db(num_customers=100):
    """
    Creates a 'customers' table in the PostgreSQL database and populates it
    with a specified number of mock customers.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("Failed to get database connection.")

        cursor = conn.cursor()

        # --- Create the customers table ---
        # Note the changes: SERIAL PRIMARY KEY for auto-increment
        # DECIMAL(12, 2) for currency, and DATE for date_of_birth
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                customer_id SERIAL PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone_number TEXT,
                address TEXT,
                date_of_birth DATE NOT NULL,
                account_type TEXT NOT NULL,
                balance DECIMAL(12, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("Table 'customers' created successfully (or already exists).")

        # --- Generate and insert mock data ---
        customers_to_add = []
        account_types = ['Savings', 'Checking', 'Investment']

        for _ in range(num_customers):
            first_name = fake.first_name()
            last_name = fake.last_name()
            email = fake.unique.email()
            phone_number = fake.phone_number()
            address = fake.address().replace('\n', ', ')
            date_of_birth = fake.date_of_birth(
                minimum_age=18, maximum_age=90).strftime('%Y-%m-%d')
            account_type = random.choice(account_types)
            balance = round(random.uniform(50.00, 50000.00), 2)

            customers_to_add.append((
                first_name,
                last_name,
                email,
                phone_number,
                address,
                date_of_birth,
                account_type,
                balance
            ))

        # Use executemany for efficient bulk insertion
        # Note the change: placeholders are %s instead of ?
        insert_query = '''
            INSERT INTO customers (
                first_name, last_name, email, phone_number, address,
                date_of_birth, account_type, balance
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO NOTHING
        '''
        cursor.executemany(insert_query, customers_to_add)

        # Commit the changes to the database
        conn.commit()
        print(
            f"Successfully inserted/updated {len(customers_to_add)} mock customers.")

    except (psycopg2.Error, Exception) as e:
        print(f"An error occurred: {e}")
        if conn:
            conn.rollback()  # Roll back changes on error
    finally:
        # Ensure the connection is closed
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            print("Database connection closed.")


# --- Run the function ---
if __name__ == "__main__":
    create_and_populate_db()
