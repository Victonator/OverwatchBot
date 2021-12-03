drop schema if exists OverwatchStats;
create schema OverwatchStats;
use OverwatchStats;

drop table if exists Games;
drop table if exists User;

create table User(
userID int auto_increment primary key,
discordID varchar(255) not null,
battleTag varchar(255) not null);

create table Games(
gameID int auto_increment primary key,
userID int not null,
tankRank int,
damageRank int,
supportRank int,
gameDate datetime not null,
constraint usergames foreign key(userID) references User(userID) on delete cascade);