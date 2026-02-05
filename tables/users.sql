create table users (
	userID int NOT NULL AUTO_INCREMENT,
    userName varchar(255) NOT NULL,
    password varchar(512) NOT NULL,
    role varchar(20) NOT NULL default 'user'
    CHECK (role in ('user', 'admin')),
    PRIMARY KEY (userID),
    UNIQUE (username)
);

select * from users