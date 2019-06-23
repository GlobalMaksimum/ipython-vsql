import re
from IPython.core.magic import Magics, magics_class, cell_magic, line_magic, needs_local_scope
from IPython.display import display_javascript
try:
    from traitlets.config.configurable import Configurable
    from traitlets import Bool, Int, Unicode
except ImportError:
    from IPython.config.configurable import Configurable
    from IPython.utils.traitlets import Bool, Int, Unicode
try:
    from pandas.core.frame import DataFrame, Series
except ImportError:
    DataFrame = None
    Series = None

from sqlalchemy.exc import ProgrammingError, OperationalError

import vsql.connection
import vsql.parse
import vsql.run
import vertica_python
import os
import pandas as pd


def get_connection_dict():
    assert 'VERTICA_HOST' in os.environ, 'Ensure that `vertica.host` is set in your environment.'
    assert 'VERTICA_USER' in os.environ, 'Ensure that `vertica.user` is set in your environment.'
    assert 'VERTICA_PASSWORD' in os.environ, 'Ensure that `vertica.password` is set in your environment.'
    assert 'VERTICA_DB' in os.environ, 'Ensure that `vertica.db` is set in your environment.'

    return {'host': os.environ['VERTICA_HOST'],
            'port': os.environ.get('VERTICA_PORT', 5433),
            'user': os.environ['VERTICA_USER'],
            'password': os.environ['VERTICA_PASSWORD'],
            'database': os.environ['VERTICA_DB'],
            # autogenerated session label by default,
            'session_label': os.environ.get('VERTICA_LABEL', 'vsql magic session'),
            # default throw error on invalid UTF-8 results
            'unicode_error': 'strict',
            # SSL is disabled by default
            'ssl': False,
            # using server-side prepared statements is disabled by default
            'use_prepared_statements': False,
            # connection timeout is not enabled by default
            'connection_timeout': os.environ.get('VERTICA_TIMEOUT', 5)}


@magics_class
class VerticaSqlMagic(Magics, Configurable):
    """Runs SQL statement on a database, specified by SQLAlchemy connect string.

    Provides the %%sql magic."""

    autolimit = Int(0, config=True, allow_none=True,
                    help="Automatically limit the size of the returned result sets")
    style = Unicode('DEFAULT', config=True,
                    help="Set the table printing style to any of prettytable's defined styles (currently DEFAULT, MSWORD_FRIENDLY, PLAIN_COLUMNS, RANDOM)")
    short_errors = Bool(
        True, config=True, help="Don't display the full traceback on SQL Programming Error")
    displaylimit = Int(None, config=True, allow_none=True,
                       help="Automatically limit the number of rows displayed (full result set is still stored)")
    autopandas = Bool(
        False, config=True, help="Return Pandas DataFrames instead of regular result sets")
    column_local_vars = Bool(
        False, config=True, help="Return data into local variables from column names")
    feedback = Bool(True, config=True,
                    help="Print number of rows affected by DML")
    dsn_filename = Unicode('odbc.ini', config=True, help="Path to DSN file. "
                           "When the first argument is of the form [section], "
                           "a sqlalchemy connection string is formed from the "
                           "matching section in the DSN file.")
    autocommit = Bool(True, config=True, help="Set autocommit mode")

    def __init__(self, shell):
        Configurable.__init__(self, config=shell.config)
        Magics.__init__(self, shell=shell)

        # Add ourself to the list of module configurable via %config
        self.shell.configurables.append(self)

    @needs_local_scope
    @line_magic('vsql')
    @cell_magic('vsql')
    def execute(self, line, cell='', local_ns={}):
        """Runs SQL statement against a database, specified by SQLAlchemy connect string.

        If no database connection has been established, first word
        should be a SQLAlchemy connection string, or the user@db name
        of an established connection.

        Examples::

          %%sql postgresql://me:mypw@localhost/mydb
          SELECT * FROM mytable

          %%sql me@mydb
          DELETE FROM mytable

          %%sql
          DROP TABLE mytable

        SQLAlchemy connect string syntax examples:

          postgresql://me:mypw@localhost/mydb
          sqlite://
          mysql+pymysql://me:mypw@localhost/mydb

        """
        # save globals and locals so they can be referenced in bind vars
        user_ns = self.shell.user_ns.copy()
        user_ns.update(local_ns)

        parsed = vsql.parse.parse('%s\n%s' % (line, cell), self)
        flags = parsed['flags']
        try:

            with vertica_python.connect(**get_connection_dict()) as conn:
                result = pd.read_sql(parsed['sql'], conn)

                return result

        except Exception as e:
            print(e)
            print(sql.connection.Connection.tell_format())
            return None

        try:
            result = sql.run.run(conn, parsed['sql'], self, user_ns)

            if result is not None and not isinstance(result, str) and self.column_local_vars:
                # Instead of returning values, set variables directly in the
                # users namespace. Variable names given by column names

                if self.autopandas:
                    keys = result.keys()
                else:
                    keys = result.keys
                    result = result.dict()

                if self.feedback:
                    print('Returning data to local variables [{}]'.format(
                        ', '.join(keys)))

                self.shell.user_ns.update(result)

                return None
            else:

                if flags.get('result_var'):
                    result_var = flags['result_var']
                    print("Returning data to local variable {}".format(result_var))
                    self.shell.user_ns.update({result_var: result})
                    return None

                # Return results into the default ipython _ variable
                return result

        except (ProgrammingError, OperationalError) as e:
            # Sqlite apparently return all errors as OperationalError :/
            if self.short_errors:
                print(e)
            else:
                raise

    legal_sql_identifier = re.compile(r'^[A-Za-z0-9#_$]+')


def load_ipython_extension(ip):
    """Load the extension in IPython."""

    # this fails in both Firefox and Chrome for OS X.
    # I get the error: TypeError: IPython.CodeCell.config_defaults is undefined

    # js = "IPython.CodeCell.config_defaults.highlight_modes['magic_sql'] = {'reg':[/^%%sql/]};"
    # display_javascript(js, raw=True)
    ip.register_magics(VerticaSqlMagic)
