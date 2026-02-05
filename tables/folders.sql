create table folders (
	folderID int NOT NULL AUTO_INCREMENT,
	userID int NOT NULL,
    folderName varchar(255) NOT NULL,
	parentFolderID int NULL,
    serverPath varchar(512) NOT NULL,
    createdAt datetime NOT NULL,
    lastModified datetime NOT NULL,
    
    primary key (folderID),
    foreign key (userID) references users(userID),
    foreign key (parentFolderID) references folders(folderID)
);

select * from folders