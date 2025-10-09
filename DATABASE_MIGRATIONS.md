# Database Migrations Guide

This guide explains how to manage database migrations in the VAULTA project using Alembic.

## Overview

Alembic is a database migration tool for SQLAlchemy. It allows you to version control your database schema changes and apply them incrementally.

## Prerequisites

- Alembic should be installed (included in requirements.txt)
- Database connection configured in `alembic.ini`
- SQLAlchemy models defined in `models.py`

## Basic Migration Commands

### 1. Create a New Migration

When you make changes to your models (add/remove tables, columns, etc.), create a migration:

```bash
alembic revision --autogenerate -m "migration message"
```

**Examples:**
```bash
# Adding a new table
alembic revision --autogenerate -m "add payments table"

# Adding a column
alembic revision --autogenerate -m "add admin_approved_by to payments"

# Modifying a column
alembic revision --autogenerate -m "change amount column type in transactions"

# Adding foreign key relationship
alembic revision --autogenerate -m "add transaction_id foreign key to payments"
```

### 2. Apply Migrations

To apply all pending migrations to your database:

```bash
alembic upgrade head
```

### 3. Check Migration Status

See current migration status:

```bash
alembic current
```

See migration history:

```bash
alembic history
```

## Migration Workflow

### Step-by-Step Process

1. **Make changes to your models** in `models.py`
   ```python
   # Example: Add a new column
   class Payment(Base):
       # ... existing columns ...
       admin_approved_by = Column(String, nullable=True)  # New column
   ```

2. **Generate migration**
   ```bash
   alembic revision --autogenerate -m "add admin_approved_by to payments"
   ```

3. **Review the generated migration file** in `alembic/versions/`
   ```python
   # Example generated migration
   def upgrade():
       op.add_column('payments', sa.Column('admin_approved_by', sa.String(), nullable=True))

   def downgrade():
       op.drop_column('payments', 'admin_approved_by')
   ```

4. **Apply the migration**
   ```bash
   alembic upgrade head
   ```

## Common Migration Scenarios

### Adding a New Table

1. Define the model in `models.py`:
   ```python
   class NewTable(Base):
       __tablename__ = "new_table"
       id = Column(Integer, primary_key=True, index=True)
       name = Column(String, nullable=False)
   ```

2. Generate migration:
   ```bash
   alembic revision --autogenerate -m "add new_table"
   ```

3. Apply migration:
   ```bash
   alembic upgrade head
   ```

### Adding a Column

1. Add column to existing model:
   ```python
   class User(Base):
       # ... existing columns ...
       new_field = Column(String, nullable=True)  # New column
   ```

2. Generate and apply:
   ```bash
   alembic revision --autogenerate -m "add new_field to users"
   alembic upgrade head
   ```

### Adding Foreign Key Relationships

1. Add foreign key column:
   ```python
   class Payment(Base):
       # ... existing columns ...
       transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
   ```

2. Generate and apply:
   ```bash
   alembic revision --autogenerate -m "add transaction_id foreign key to payments"
   alembic upgrade head
   ```

### Modifying Column Types

1. Change column definition:
   ```python
   class Transaction(Base):
       # Change from Integer to String
       amount = Column(String, nullable=False)  # Was: Column(Integer, nullable=False)
   ```

2. Generate and apply:
   ```bash
   alembic revision --autogenerate -m "change amount type from integer to string"
   alembic upgrade head
   ```

## Advanced Commands

### Rollback to Previous Migration

```bash
# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision_id>

# Rollback to base (empty database)
alembic downgrade base
```

### Manual Migration Creation

For complex changes that autogenerate can't handle:

```bash
alembic revision -m "manual migration description"
```

Then edit the generated file manually.

### Show SQL Without Executing

```bash
# See what SQL would be executed
alembic upgrade head --sql

# See SQL for specific migration
alembic upgrade <revision_id> --sql
```

## Best Practices

### 1. Always Review Generated Migrations

- Check the generated migration file before applying
- Ensure it matches your intended changes
- Add any necessary data migrations

### 2. Use Descriptive Migration Messages

```bash
# Good
alembic revision --autogenerate -m "add payment approval workflow with admin fields"

# Bad
alembic revision --autogenerate -m "update"
```

### 3. Test Migrations

- Test migrations on a copy of production data
- Ensure both upgrade and downgrade work correctly
- Verify data integrity after migration

### 4. Backup Before Major Migrations

```bash
# Example backup command (adjust for your database)
pg_dump vaulta > backup_before_migration.sql
```

### 5. Handle Data Migrations

For migrations that require data transformation:

```python
def upgrade():
    # Schema change
    op.add_column('users', sa.Column('full_name', sa.String(), nullable=True))
    
    # Data migration
    connection = op.get_bind()
    connection.execute(
        "UPDATE users SET full_name = first_name || ' ' || last_name"
    )
```

## Troubleshooting

### Common Issues

1. **"Target database is not up to date"**
   ```bash
   alembic upgrade head
   ```

2. **Migration conflicts**
   ```bash
   alembic history
   alembic merge heads -m "merge migrations"
   ```

3. **Autogenerate not detecting changes**
   - Ensure models are imported in `alembic/env.py`
   - Check if changes are actually different from current schema

### Fixing Issues

1. **Reset to clean state** (DANGEROUS - only for development):
   ```bash
   alembic downgrade base
   alembic upgrade head
   ```

2. **Manual schema sync**:
   ```bash
   alembic stamp head  # Mark current schema as up-to-date
   ```

## Project-Specific Notes

### Current Models
- `User` - User accounts
- `OTP` - One-time passwords
- `ApiKey` - API authentication keys
- `Customer` - Customer information
- `Transaction` - Financial transactions
- `Account` - User accounts/wallets
- `Payment` - Payment requests with approval workflow

### Recent Changes
- Added `transaction_id` foreign key to Payment table
- Added admin approval fields to Payment table
- Enhanced Transaction table with description field

## File Structure

```
/VAULTA/
├── alembic/
│   ├── versions/          # Migration files
│   ├── env.py            # Alembic environment
│   └── script.py.mako    # Migration template
├── alembic.ini           # Alembic configuration
├── models.py             # SQLAlchemy models
└── database.py           # Database connection
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `alembic revision --autogenerate -m "message"` | Create new migration |
| `alembic upgrade head` | Apply all pending migrations |
| `alembic current` | Show current migration |
| `alembic history` | Show migration history |
| `alembic downgrade -1` | Rollback one migration |
| `alembic upgrade head --sql` | Show SQL without executing |

---

**Remember**: Always backup your database before running migrations in production!