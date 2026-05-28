CREATE TABLE interest_tags (
    tag         TEXT PRIMARY KEY,
    category    TEXT NOT NULL,
    sort_order  INT NOT NULL DEFAULT 0
);

INSERT INTO interest_tags (tag, category, sort_order) VALUES
    ('AI/ML',           'Tech',   1),
    ('Web Dev',         'Tech',   2),
    ('Mobile',          'Tech',   3),
    ('DevOps',          'Tech',   4),
    ('Data',            'Tech',   5),
    ('Cybersecurity',   'Tech',   6),
    ('Open Source',     'Tech',   7),
    ('Blockchain',      'Tech',   8),
    ('Fintech',         'Domain', 1),
    ('Healthtech',      'Domain', 2),
    ('Edtech',          'Domain', 3),
    ('Climate',         'Domain', 4),
    ('SaaS',            'Domain', 5),
    ('Consumer',        'Domain', 6),
    ('B2B',             'Domain', 7),
    ('Deep Tech',       'Domain', 8),
    ('Founder',         'Role',   1),
    ('Engineer',        'Role',   2),
    ('Designer',        'Role',   3),
    ('PM',              'Role',   4),
    ('Marketer',        'Role',   5),
    ('Researcher',      'Role',   6),
    ('Investor',        'Role',   7),
    ('Student',         'Role',   8),
    ('Hiring',          'Goals',  1),
    ('Job Hunting',     'Goals',  2),
    ('Cofounder Search','Goals',  3),
    ('Investing',       'Goals',  4),
    ('Mentoring',       'Goals',  5),
    ('Collaborating',   'Goals',  6),
    ('Learning',        'Goals',  7);

GRANT SELECT ON interest_tags TO anon, authenticated;
