import pytest
import unittest


@pytest.mark.parametrize("user_password_host_port, kwargs, expected", [
    ("localhost", {}, (None, None, "localhost", 3306)),
    ("localhost:1238", {}, (None, None, "localhost", 1238)),
    ("localhost", {"default_port": 1238}, (None, None, "localhost", 1238)),
    ("bob:secret@mysql.somewhere.org:1238", {}, ("bob", "secret", "mysql.somewhere.org", 1238)),
    ("bob:sec@r:et2#@mysql.somewhere.org:1238", {}, ("bob", "sec@r:et2#", "mysql.somewhere.org", 1238)),
    ("bob:@mysql.somewhere.org:1238", {}, ("bob", "", "mysql.somewhere.org", 1238)),
    ("bob@mysql.somewhere.org:1238", {}, ("bob", None, "mysql.somewhere.org", 1238)),
    ("bob:sec@r:et2#@mysql.somewhere.org", {}, ("bob", "sec@r:et2#", "mysql.somewhere.org", 3306)),
    ("@mysql.somewhere.org:1238", {}, (None, None, "mysql.somewhere.org", 1238)),
    ("bob:sec@r:et2#@mysql.somewhere.org", {"return_dict": True},
     {"user": "bob", "password": "sec@r:et2#", "host": "mysql.somewhere.org", "port": 3306})
])
def test_get_user_password_host_port(user_password_host_port, kwargs, expected):
    from akrr.util.sql import get_user_password_host_port
    assert get_user_password_host_port(user_password_host_port, **kwargs) == expected


@pytest.mark.parametrize("user_password_host_port_db, kwargs, expected", [
    ("localhost", {}, (None, None, "localhost", 3306, None)),
    ("localhost:1238", {}, (None, None, "localhost", 1238, None)),
    ("localhost", {"default_port": 1238}, (None, None, "localhost", 1238, None)),
    ("bob:secret@mysql.somewhere.org:1238", {}, ("bob", "secret", "mysql.somewhere.org", 1238, None)),
    ("bob:sec@r:et2#@mysql.somewhere.org:1238", {}, ("bob", "sec@r:et2#", "mysql.somewhere.org", 1238, None)),
    ("bob:@mysql.somewhere.org:1238", {}, ("bob", "", "mysql.somewhere.org", 1238, None)),
    ("bob@mysql.somewhere.org:1238", {}, ("bob", None, "mysql.somewhere.org", 1238, None)),
    ("bob:sec@r:et2#@mysql.somewhere.org", {}, ("bob", "sec@r:et2#", "mysql.somewhere.org", 3306, None)),
    ("@mysql.somewhere.org:1238", {}, (None, None, "mysql.somewhere.org", 1238, None)),
    ("bob:sec@r:et2#@mysql.somewhere.org", {"return_dict": True},
        {"user": "bob", "password": "sec@r:et2#", "host": "mysql.somewhere.org", "port": 3306, "database": None}),
    ("localhost:1238", {"default_database": "mod_akrr2"}, (None, None, "localhost", 1238, "mod_akrr2")),
    ("localhost:/mod_akrr", {}, (None, None, "localhost", 3306, "mod_akrr")),
    ("localhost:1238:/mod_akrr", {}, (None, None, "localhost", 1238, "mod_akrr")),
    ("localhost:/mod_akrr", {"default_port": 1238}, (None, None, "localhost", 1238, "mod_akrr")),
    ("bob:secret@mysql.somewhere.org:1238:/mod_akrr", {}, ("bob", "secret", "mysql.somewhere.org", 1238, "mod_akrr")),
    ("bob:sec@r:et2#@mysql.somewhere.org:1238:/mod_akrr", {},
        ("bob", "sec@r:et2#", "mysql.somewhere.org", 1238, "mod_akrr")),
    ("bob:@mysql.somewhere.org:1238:/mod_akrr", {}, ("bob", "", "mysql.somewhere.org", 1238, "mod_akrr")),
    ("bob@mysql.somewhere.org:1238:/mod_akrr", {}, ("bob", None, "mysql.somewhere.org", 1238, "mod_akrr")),
    ("bob:sec@r:et2#@mysql.somewhere.org:/mod_akrr", {},
        ("bob", "sec@r:et2#", "mysql.somewhere.org", 3306, "mod_akrr")),
    ("@mysql.somewhere.org:1238:/mod_akrr", {}, (None, None, "mysql.somewhere.org", 1238, "mod_akrr")),
    ("bob:sec@r:et2#@mysql.somewhere.org:/mod_akrr", {"return_dict": True},
        {"user": "bob", "password": "sec@r:et2#", "host": "mysql.somewhere.org", "port": 3306, "database": "mod_akrr"})
])
def test_get_user_password_host_port_db(user_password_host_port_db, kwargs, expected):
    from akrr.util.sql import get_user_password_host_port_db
    assert get_user_password_host_port_db(user_password_host_port_db, **kwargs) == expected


@pytest.mark.parametrize("expected, args", [
    ("localhost", (None, None, "localhost", None, None)),
    ("localhost:1238", (None, None, "localhost", 1238, None)),
    ("bob:secret@mysql.somewhere.org:1238", ("bob", "secret", "mysql.somewhere.org", 1238, None)),
    ("bob:sec@r:et2#@mysql.somewhere.org:1238", ("bob", "sec@r:et2#", "mysql.somewhere.org", 1238, None)),
    ("bob:@mysql.somewhere.org:1238", ("bob", "", "mysql.somewhere.org", 1238, None)),
    ("bob@mysql.somewhere.org:1238", ("bob", None, "mysql.somewhere.org", 1238, None)),
    ("bob:sec@r:et2#@mysql.somewhere.org", ("bob", "sec@r:et2#", "mysql.somewhere.org", None, None)),
    ("mysql.somewhere.org:1238", (None, None, "mysql.somewhere.org", 1238, None)),
    ("localhost:1238", (None, None, "localhost", 1238, None)),
    ("localhost:/mod_akrr", (None, None, "localhost", None, "mod_akrr")),
    ("localhost:1238:/mod_akrr", (None, None, "localhost", 1238, "mod_akrr")),
    ("localhost:/mod_akrr", (None, None, "localhost", None, "mod_akrr")),
    ("bob:secret@mysql.somewhere.org:1238:/mod_akrr", ("bob", "secret", "mysql.somewhere.org", 1238, "mod_akrr")),
    ("bob:sec@r:et2#@mysql.somewhere.org:1238:/mod_akrr", ("bob", "sec@r:et2#", "mysql.somewhere.org", 1238, "mod_akrr")),
    ("bob:@mysql.somewhere.org:1238:/mod_akrr", ("bob", "", "mysql.somewhere.org", 1238, "mod_akrr")),
    ("bob@mysql.somewhere.org:1238:/mod_akrr", ("bob", None, "mysql.somewhere.org", 1238, "mod_akrr")),
    ("bob:sec@r:et2#@mysql.somewhere.org:/mod_akrr", ("bob", "sec@r:et2#", "mysql.somewhere.org", None, "mod_akrr")),
    ("mysql.somewhere.org:1238:/mod_akrr", (None, None, "mysql.somewhere.org", 1238, "mod_akrr"))
])
def test_set_user_password_host_port_db(expected, args):
    from akrr.util.sql import set_user_password_host_port_db
    assert set_user_password_host_port_db(*args) == expected


test_data_show_grant_example = [
    ["GRANT USAGE ON *.* TO 'testuser1'@'localhost'"],
    [
        "GRANT USAGE ON *.* TO 'akrruser123'@'localhost' IDENTIFIED BY PASSWORD '*1967'",
        "GRANT ALL PRIVILEGES ON `mod_appkernel`.* TO 'akrruser123'@'localhost'",
        "GRANT SELECT ON `modw`.* TO 'akrruser123'@'localhost'",
        "GRANT ALL PRIVILEGES ON `mod_akrr`.* TO 'akrruser123'@'localhost'"
    ]
]


@pytest.mark.parametrize("db_to_check, priv_to_check, priv_list, expected", [
    ("mod_akrr", "ALL", test_data_show_grant_example[0], False),
    ("mod_akrr", "ALL", test_data_show_grant_example[1], True),
    ("dontexists", "ALL", test_data_show_grant_example[1], False),
    ("dontexists", "SELECT", test_data_show_grant_example[1], False),
    ("mod_akrr", "SELECT", test_data_show_grant_example[1], True),
    ("modw", "SELECT", test_data_show_grant_example[1], True),
    ("modw", "ALL", test_data_show_grant_example[1], False)
])
def test__db_check_priv__identify_priv(db_to_check, priv_to_check, priv_list, expected):
    from akrr.util.sql import _db_check_priv__identify_priv as f
    assert f(db_to_check, priv_to_check, priv_list) is expected


@pytest.mark.sql
class Test_akrr_util_sql_Functions_with_SQL(unittest.TestCase):
    """this tests require MySQL server"""

    def __init__(self,methodName='runTest'):
        super(Test_akrr_util_sql_Functions_with_SQL, self).__init__(methodName=methodName)

        self.su_sql = "root:root@localhost"

        self.user1 = "testuser1"
        self.password1 = ""

        self.db1 = "sillydb1"
        self.db2 = "sillydb2"

    def test_db_check_priv(self):
        from akrr.util.sql import get_user_password_host_port
        from akrr.util.sql import get_db_client_host
        from akrr.util.sql import get_con_to_db
        from akrr.util.sql import db_check_priv
        from akrr.util.sql import cv
        from akrr.util.sql import create_user_if_not_exists

        su_user, \
        su_password, \
        db_host, \
        db_port = get_user_password_host_port(self.su_sql)

        su_con, su_cur = get_con_to_db(su_user, su_password, db_host, db_port)

        client_host = get_db_client_host(su_cur)

        # create user
        create_user_if_not_exists(su_con, su_cur, self.user1, self.password1, client_host)

        # check su rights
        self.assertEqual(db_check_priv(su_cur, "mysql", "ALL"), True)
        self.assertEqual(db_check_priv(su_cur, "dontexists", "ALL"), True)
        self.assertEqual(db_check_priv(su_cur, "mysql", "ALL", self.user1), False)
        self.assertEqual(db_check_priv(su_cur, "dontexists", "ALL", self.user1), False)
        self.assertEqual(db_check_priv(su_cur, "mysql", "ALL", self.user1, client_host), False)
        self.assertEqual(db_check_priv(su_cur, "dontexists", "ALL", self.user1, client_host), False)

        # connect as user
        _, cur = get_con_to_db(self.user1, self.password1, "localhost")
        self.assertEqual(db_check_priv(su_cur, "dontexists", "ALL", self.user1), False)

        # create db and give permission to user1
        su_cur.execute("CREATE DATABASE IF NOT EXISTS %s CHARACTER SET utf8" % (cv(self.db1),))
        su_cur.execute("CREATE DATABASE IF NOT EXISTS %s CHARACTER SET utf8" % (cv(self.db2),))
        su_con.commit()

        su_cur.execute("GRANT ALL ON " + cv(self.db1) + ".* TO %s@%s", (self.user1, client_host))
        su_cur.execute("GRANT SELECT ON " + cv(self.db2) + ".* TO %s@%s", (self.user1, client_host))
        su_con.commit()

        # check rights as current regular user
        self.assertEqual(db_check_priv(cur, "mysql", "ALL"), False)
        self.assertEqual(db_check_priv(cur, self.db1, "ALL"), True)
        self.assertEqual(db_check_priv(cur, self.db1, "SELECT"), True)
        self.assertEqual(db_check_priv(cur, self.db2, "ALL"), False)
        self.assertEqual(db_check_priv(cur, self.db2, "SELECT"), True)

    def _clean_db(self):
        from akrr.util.sql import get_db_client_host
        from akrr.util.sql import get_user_password_host_port
        from akrr.util.sql import get_con_to_db
        from akrr.util.sql import cv
        from akrr.util.sql import drop_user_if_exists

        su_user, \
        su_password, \
        db_host, \
        db_port = get_user_password_host_port(self.su_sql)

        _, su_cur = get_con_to_db(su_user, su_password, db_host, db_port)
        client_host = get_db_client_host(su_cur)

        # remove db
        su_cur.execute("DROP DATABASE IF EXISTS %s" % (cv(self.db1),))
        su_cur.execute("DROP DATABASE IF EXISTS %s" % (cv(self.db2),))

        # remove user
        drop_user_if_exists(su_cur, self.user1, client_host)

    def tearDown(self):
        self._clean_db()
        unittest.TestCase.tearDown(self)
