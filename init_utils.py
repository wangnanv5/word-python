import click
from word_back.database import Base, engine

@click.group()
@click.version_option("1.0.0", prog_name="filetool")
def cli():
    pass

# uv run .\init_utils.py create-db
# @cli.command(name="create_db")
@cli.command()
def create_db():
    from word_back.models import WordBook
    Base.metadata.create_all(bind=engine)
    click.echo(click.style(f"数据库创建成功", fg="green", bold=True))

    
if __name__ == "__main__":
    cli()