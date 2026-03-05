import re
import sys
import asyncio

import click

sys.path.append('source')

from db.base import AsyncDatabaseSession

PASSWORD_PATTERN = re.compile(r'^(?=.*[A-Z])(?=.*\d).{8,}$')


def validate_password(password: str) -> str:
    if not PASSWORD_PATTERN.match(password):
        raise click.BadParameter('Must be 8+ chars with at least one uppercase letter and one digit.')
    return password


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


@click.group()
def cli():
    """S1P management commands."""
    pass


@cli.command()
@click.option('--email', prompt=True, help='Owner email address')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Owner password')
@click.option('--first-name', prompt='First name', help='Owner first name')
@click.option('--last-name', prompt='Last name', default='', help='Owner last name')
@click.option('--phone', default=None, help='Owner phone number')
def createsuperuser(email, password, first_name, last_name, phone):
    """Create a new owner (superuser) account."""
    validate_password(password)
    from db.models.owner import Owner
    from utils.managers import PasswordManager

    async def _create():
        async with AsyncDatabaseSession._session_factory() as session:
            existing = await Owner.get(email=email, session=session)
            if existing:
                click.echo(click.style(f'Error: Owner with email "{email}" already exists.', fg='red'))
                return

            owner = await Owner.create(
                session=session,
                first_name=first_name,
                last_name=last_name or None,
                email=email,
                phone=phone,
                password_hash=PasswordManager.hash(password),
                is_active=True,
                email_verified=True,
            )
            click.echo(click.style(f'Owner created: {owner.email} (id: {owner.id})', fg='green'))

    run_async(_create())


@cli.command()
def listowners():
    """List all owner accounts."""
    from db.models.owner import Owner

    async def _list():
        async with AsyncDatabaseSession._session_factory() as session:
            owners = await Owner.get_all(session=session)
            if not owners:
                click.echo('No owners found.')
                return

            click.echo(f'{"ID":<38} {"Email":<30} {"Name":<25} {"Active":<8}')
            click.echo('-' * 101)
            for o in owners:
                click.echo(f'{str(o.id):<38} {o.email:<30} {o.full_name:<25} {"Yes" if o.is_active else "No":<8}')

    run_async(_list())


@cli.command()
@click.argument('email')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='New password')
def changepassword(email, password):
    """Change an owner's password."""
    validate_password(password)
    from db.models.owner import Owner
    from utils.managers import PasswordManager

    async def _change():
        async with AsyncDatabaseSession._session_factory() as session:
            owner = await Owner.get(email=email, session=session)
            if not owner:
                click.echo(click.style(f'Error: Owner with email "{email}" not found.', fg='red'))
                return

            await Owner.update(
                session=session,
                id=owner.id,
                password_hash=PasswordManager.hash(password),
            )
            click.echo(click.style(f'Password changed for {email}.', fg='green'))

    run_async(_change())


if __name__ == '__main__':
    cli()
