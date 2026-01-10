create table users (
	userID int NOT NULL AUTO_INCREMENT,
    userName varchar(255) NOT NULL,
    password varchar(512),
    PRIMARY KEY (userID)
);

select * from users