#!/usr/bin/python

# imported by interface.py and mailer.py
import os
import csv

# new for python3
import pymysql
pymysql.install_as_MySQLdb()

import MySQLdb
# import MySQLdb.cursors
import datetime            # needed to read TIME from SQL

from subprocess import call
import subprocess
from sys import stdin
import glob                 # for reading files in directory
from xml.etree import ElementTree as et  # to modify sting xml file for android
import npyscreen as nps

# from sqlalchemy import create_engine    # fix for pandas sql connections

import interface_ini as db     # reads the database and file path information from meter_ini.py

def connectDatabase(_dbHost):
    """ try to connect to server - else to local database """
    global cursor
    global dbConnection
    global dbHost
    dbHost = _dbHost
    try:
        dbConnection = MySQLdb.connect(host=db.Host, user=db.User, passwd= db.Pass, db=db.Name, cursorclass = MySQLdb.cursors.DictCursor)
        cursor = dbConnection.cursor()
    except:
        dbHost='localhost'
        dbConnection = MySQLdb.connect(host=db.Host, user=db.User, passwd= db.Pass, db=db.Name, cursorclass = MySQLdb.cursors.DictCursor)
        cursor = dbConnection.cursor()
    return cursor

def connectPandasDatabase():
    # engine = create_engine("mysql+mysqldb://USER:"+'PASSWORD'+"@localhost/DATABASE")
    #/ removed 7 Apr 2019
    # suspect this wasnt used
    print("phil removed create_engine")
    # engine = create_engine("mysql+mysqldb://{}:{}@{}/{}".format(dbUser,dbPass,dbHost,dbName))
    engine = False
    return engine


def getHost():
    return dbHost

def getConnection():
    return dbConnection

def connectDatabaseOLD(_dbHost):
    """ remove """
    global dbConnection
    global dbHost
    dbHost = _dbHost
    try:
        dbConnection = MySQLdb.connect(host=db.Host, user=db.User, passwd= db.Pass, db=db.Name)
        cursor = dbConnection.cursor()
    except:
        dbHost='localhost'
        dbConnection = MySQLdb.connect(host=db.Host, user=db.User, passwd= db.Pass, db=db.Name)
        cursor = dbConnection.cursor()
    return cursor

def commit():
    global dbConnection
    dbConnection.commit()

def executeSQL(_sqlq):
    """ to safeguard against dropped connections """
    global cursor
    try:
        cursor.execute(_sqlq)
    except:
        message("Reconnect to datahase")
        cursor = connectDatabase(dbHost)
        message(_sqlq)
        cursor.execute(_sqlq)
    return cursor.lastrowid

def getSQL(_sqlq):
    """ to safeguard against dropped connections """
    global cursor
    try:
        cursor.execute(_sqlq)
    except:
        message("Need to reconnect to datahase to get SQL")
        cursor = connectDatabase(dbHost)
        cursor.execute(_sqlq)
    return cursor.fetchall()

def toggleDatabase():
    """ switch between remote and local db """
    global dbHost
    global cursor
    if (dbHost == 'localhost'):
        dbHost = '109.74.196.205'
    else:
        dbHost = 'localhost'
    cursor = connectDatabase(dbHost)

def backup_database():
    """ dump sql in local dated file """
    message('The password is: {}'.format(db.Pass))
    dateTimeToday = datetime.datetime.now()
    thisDate = dateTimeToday.strftime("%Y_%m_%d")
    call('mysqldump --column-statistics=0 -u ' + db.User + ' -h ' + db.Host + ' -p --databases ' + db.Name + ' > ' + './Data/database/' + thisDate + '_' + db.Name + '.sql', shell=True)
    message('Database backed up as ' + thisDate + '_' + db.Name + '.sql')

def getNameEmail(table,criterion):
    """ returns name and email for matched """
    email='\'%@%\''
    if (table == "Household"):
        sqlq = """
                    SELECT Contact.idContact,
                           Contact.Name,
                           Contact.email, 
                           Household.idHousehold AS idHH,
                           Household.security_code AS sc
                    From Contact
                    JOIN Household
                        ON Household.Contact_idContact = Contact.idContact
                    WHERE email LIKE %s
                        AND (Contact.status <> 'unsubscribed' OR Contact.status IS NULL)
                        AND %s
                    GROUP BY Contact.idContact;
                 """ % (email,criterion);
                 # GROUP BY ensures each contact only gets one email (even if they have many HH records)

        # THIS is for contacts who only appear once in the HH table - bit pointless?
        # sqlq = """SELECT * FROM (
        #             SELECT Contact.idContact,Contact.Name,Contact.email, Household.idHousehold AS idHH,Household.security_code AS sc
        #             From Contact
        #             JOIN Household
        #             ON Household.Contact_idContact = Contact.idContact
        #             WHERE email LIKE %s
        #             AND (Contact.status <> 'unsubscribed' OR Contact.status IS NULL)
        #             AND %s
        #          )
        #          AS x
        #          GROUP BY idContact HAVING COUNT(*) = 1;""" % (email,criterion);
            

                    # AND Contact.status IS NULL

        # sqlq = "SELECT Contact.idContact,Contact.Name,Contact.email, Household.idHousehold AS idHH,Household.security_code AS sc\
        #         From Contact\
        #         Join Household\
        #         ON Household.Contact_idContact = Contact.idContact\
        #         WHERE email like %s AND (Contact.status <> 'unsubscribed' OR Contact.status IS NULL) AND %s" % (email,criterion)
    else:
        sqlq = """Select *
                FROM %s
                WHERE email like %s 
                AND (status <> 'unsubscribed' OR status IS NULL) 
                AND %s""" % (table,email,criterion)

    result = getSQL(sqlq)
    return result

def getRecipientCount(table,criterion):
    return len(getNameEmail(table,criterion))

def getHouseholdCount(condition):
    """ count household in database matching the modus criteria """
    sqlq = "SELECT count(idHousehold) FROM Household WHERE " + condition +";"
    result = getSQL(sqlq)[0]
    return ("%s" % result['count(idHousehold)'])

def getContact(hhID):
    """ return contactID for given household """
    sqlq = "SELECT Contact_idContact FROM Household WHERE idHousehold = '%s';" % hhID
    if (getSQL(sqlq)):
        result = getSQL(sqlq)[0]
        return ("%s" % result['Contact_idContact'])
    else:
        message("Contact for household %s not found" % hhID)
        return '0'

def getNameOfContact(thisContactID):
    """ get Contact name for a given Contact """
    sqlq ="SELECT Name,Surname\
            FROM Contact \
            WHERE idContact = '%s';" % thisContactID
    result = getSQL(sqlq)[0]
    return str(result['Name']) + ' ' + str(result['Surname'])

def getSecurityCode(householdID):
    """ get the security code for this household """
    sqlq = "SELECT security_code FROM Household WHERE idHousehold = '%s';" % householdID 
    result = getSQL(sqlq)[0]
    return ("%s" % result['security_code'])

def householdExists(hhID):
    """ true if record is found """
    sqlq = "SELECT * FROM Household WHERE idHousehold = %s;" % hhID
    if (getSQL(sqlq)):
        return True
    else:
        return False

def getHouseholdForContact(contactID):
    """ find the first HH match for this cID - WARNING - there could be more than one!!! """
    sqlq = "SELECT idHousehold FROM Household WHERE Contact_idContact = %s;" % contactID
    if (getSQL(sqlq)):
        result = getSQL(sqlq)[0]
        return ("%s" % result['idHousehold'])
    else:
        message("No contact with ID=%s found"% contactID)
        return '0'
        

def getHouseholdsForContact(contactID):
    """ returns a list of HH IDs """
    sqlq = "SELECT idHousehold FROM Household WHERE Contact_idContact = %s;" % contactID
    hhIDs = []
    results = getSQL(sqlq)
    for result in results:
        hhIDs.append("{}".format(result['idHousehold']))
    return hhIDs
        

def getHouseholdForMeta(_metaID):
    """ find the one match of HH for this metaID """
    sqlq = "SELECT Household_idHousehold FROM Meta WHERE idMeta = %s;" % _metaID
    if (getSQL(sqlq)):
        result = getSQL(sqlq)[0]
        return ("%s" % result['Household_idHousehold'])
    else:
        message("Meta ID %s not found"%_metaID)
        return '0'


def getStatus(householdID):
    """ get the status for this household """
    sqlq = "SELECT status FROM Household WHERE idHousehold = '%s';" % householdID 
    result = getSQL(sqlq)[0]
    return ("%s" % result['status'])
# def getStatus(householdID):
#     # get the status for this household
#     sqlq = "SELECT status FROM Household WHERE idHousehold = '" + householdID + "'"
#     executeSQL(sqlq)
#     return ("%s" % (cursor.fetchone()))

def getDateTimeFormated(dts):
    """ DateTimeString as received from database: return 31 Jan 16 """
    # http://strftime.org/
    if (dts != 'None'):
        f = '%Y-%m-%d %H:%M:%S'
        this_dt = datetime.datetime.strptime(dts, f)
        return this_dt.strftime("%-d %b %y")
    else:
        return "None"


def getSpamContacts():
    sqlq = """
        SELECT idContact FROM Household 
             JOIN Contact
             ON idContact = Contact_idContact
             WHERE page_number = 0
             AND Contact.status = 'eu';
        """
    results = getSQL(sqlq)
    contactIDs = []
    for contact in results:
       contactIDs.append(contact['idContact'])
    return contactIDs

def deleteEntryID(dataType,idEntry):
    """ delete entry and associated data 
        when deleting a Contact ALL associted Households will also be removed
        if the entry was last in, the indexing is reset to allow it to be re-entered with the same ID
    """
    if (dataType == 'm'):
        table = "Meta"
    elif (dataType == 'c'):
        table = "Contact"
        hhIDs = getHouseholdsForContact(idEntry)
        for hhID in hhIDs:
            deleteEntryID('h',hhID)
    elif (dataType == 'h'):
        table = "Household"
    else:
        message("Identify table with _h_ousehold,_c_ontact,_m_eta")
        return

    # get value of last entry (so that if we delete the last one, we can reset the auto increment)
    sqlq = "SELECT MAX(id{table}) AS maxEntry FROM {table};".format(table=table)
    result = getSQL(sqlq)[0]
    maxEntry = str(result['maxEntry'])

    sqlq = "SELECT * FROM {table} Where id{table} = {id}".format(table=table, id=idEntry)
    result = getSQL(sqlq)[0]
    text = ""
    keys = result.keys()
    for key in keys:
        text = "{}{}: {}\n".format(text,key,result[key])
    confirmed = nps.notify_ok_cancel(text,"Delete this entry?",editw=2)
    if not confirmed:
        return

    sqlq = "DELETE FROM {table} Where id{table} = {id}".format(table=table, id=idEntry)
    executeSQL(sqlq)
    commit()

    if (idEntry == maxEntry):
        # reset indexing
        sqlq = "ALTER TABLE {table} AUTO_INCREMENT = {id};".format(table=table, id=idEntry)
        executeSQL(sqlq)
        commit()



def formatBox(col1, col2):
    return "\t\t\t|\t\t" + "{:<19}".format(col1) + "{:<18}".format(col2) + "|"

def formatBoxList(List):
    fList = []
    for line in List:
        fList.append("\t\t\t|\t\t" + "{:<63}".format(line) + "|")
    return fList

def formatBigBox(col1, col2):
    return "\t\t\t|\t\t" + "{:<14}".format(col1) + "{:<49}".format(col2) + "|"

def formatList(col1, col2):
    return ["\t\t\t" + "{:<25}".format(col1) + "{:<30}".format(col2)]

def message(msgStr):
    """ shorthand to display debug information """
    nps.notify_confirm(msgStr,editw=1)

