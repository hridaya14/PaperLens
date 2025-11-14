SELECT 'CREATE DATABASE airflow_db'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow_db')\gexec;

