from alembic import command


def test_models_match_migrations(sessions, alembic_config):
    """Fails if app/models.py changed without a matching migration (same as `alembic check`)."""
    command.check(alembic_config)


def test_downgrade_and_upgrade_again(sessions, alembic_config):
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
