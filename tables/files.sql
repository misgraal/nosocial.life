create table files (
	fileID int NOT NULL AUTO_INCREMENT,
	userID int NOT NULL,
    fileName varchar(255) NOT NULL,
	folderID int NOT NULL,
    serverPath varchar(512) NOT NULL,
	syzeBytes int NOT NULL,
    previewPath varchar(512) NOT NULL,
    createdAt datetime NOT NULL,
    lastModified datetime NOT NULL
    
    foreign key (userID) references users(userID)
    foreign key (folderID) references folders(folderID)
);

select * from files