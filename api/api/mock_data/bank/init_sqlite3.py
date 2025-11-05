import sqlite3
import random
from faker import Faker

# Initialize the Faker library to generate mock data
fake = Faker()


def create_and_populate_db(db_name='bank.db', num_customers=100):
    """
    Creates a SQLite database with a 'customers' table and populates it
    with a specified number of mock customers.
    """
    try:
        # Establish a connection to the SQLite database.
        # This will create the database file if it doesn't exist.
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # --- Create the customers table ---
        # Using "IF NOT EXISTS" prevents an error if the script is run again.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone_number TEXT,
                address TEXT,
                date_of_birth TEXT NOT NULL,
                account_type TEXT NOT NULL,
                balance REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("Table 'customers' created successfully.")

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
        insert_query = '''
            INSERT INTO customers (
                first_name, last_name, email, phone_number, address,
                date_of_birth, account_type, balance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        cursor.executemany(insert_query, customers_to_add)

        # Commit the changes to the database
        conn.commit()
        print(f"Successfully inserted {len(customers_to_add)} mock customers.")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Ensure the connection is closed
        if conn:
            conn.close()
            print("Database connection closed.")


# --- Run the function ---
if __name__ == "__main__":
    create_and_populate_db()
