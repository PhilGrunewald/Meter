#!/usr/bin/python

# Shortcuts:
#-----------
#action_keys        single key commands
#menu_text          main screen text
#menu_bar           the pop up menu
#display_data       display data depending on displayModus
#action_highlighted action based on line selected (enter) depending on displayModus
#statusUpdate       list of and setting of household status

# ADB comands worth integrating
# Check AUTOSTART setting
# adb shell dumpsys | grep -A 2 "power off alarms dump"
# Check Battery level
# Android 4
# adb shell dumpsys battery | grep level 
# Android 6

# adb shell am force-stop org.energy_use.meter
# What apps are running
# adb shell ps

# For plotting
# import flask                  # serve python
import json                   # used for reading activities.json
import urllib                 # to read json from github
import numpy as np            # used for mean
import pandas as pd           # to reshape el readings
import textwrap               # to wrap long comments

# from bokeh.embed import components
# from bokeh.resources import INLINE
# from bokeh.util.string import encode_utf8
# 
# from bokeh.plotting import figure, curdoc, vplot, show
# from bokeh.plotting import figure, show, output_file
# from bokeh.models import Range1d, Circle

from meter import *         # db connection and npyscreen features
from meter_ini import *     # reads the database and file path information from meter_ini.py

# app = flask.Flask(__name__)
# app.config['DEBUG'] = True


# modi = [ 'Home', 'Confirmed', 'Issued', 'Processed', 'Upcoming', 'Future' , 'No date yet']
modi = [ 'aHome', 'Confirmed', 'No date yet']

Criteria = {
        'Home':     'status >= 0',
        'Upcoming':     'status < 4 AND date_choice >= CURDATE() AND date_choice < CURDATE() + INTERVAL "31" DAY ORDER BY date_choice ASC',
        'Confirmed':    'status = 4 ORDER BY date_choice ASC',
        'Issued':       'status = 5 ORDER BY date_choice ASC',
        'Processed':    'status > 5 ORDER BY date_choice DESC',
        'Future':       'date_choice > CURDATE()',
        'No date yet':  'date_choice < "2010-01-01"',
        'no reading':   'Watt < 10',
        'high reading': 'Watt > 500'
        }

Screen = {}
ActionKeys = {}
ScreenKey = '0'

householdID = '0'

SerialNumbers   = []
    
first_time = True

def showHouseholds():
    MeterApp._Forms['MAIN'].display_selected_data('Households')

def callShell(command):
    # executes shell command and returns all text displayed
    call("%s > .temp" % command, shell=True)
    messageStr = ''
    for line in open('.temp'):
        messageStr += line
    return messageStr

def showScreen(key):
    global ScreenKey
    global householdID
    Screen[ScreenKey]['Household'] = householdID


    ScreenKey = str(key)
    householdID = Screen["%s"%key]['Household']
    MeterApp._Forms['MAIN'].setMainMenu()



    
def getDateOfFirstEntry(thisFile,col):
    # Find the date string in a data file
    # expected format: ...,2016-02-22T17:00:00.000Z,...
    # in the second column
    with open(thisFile, 'r') as f:
            firstLine = f.readline()
    dateTime = firstLine.split(',')[col]
    thisDate = dateTime[0:10]
    return thisDate

def getMetaData(MetaFile, ItemName):
    # extract content from meta file (or any other file)
    content = ""
    for line in open(MetaFile):
        if ItemName in line:
            content = line.split(ItemName + ": ", 1)[1]
    return content.strip()

def data_download(*self):
    # pull files from phone
    # 7 Nov 2016: previously downloaded 'files' to filepath
    # Android 6(?) causes the 'METER folder' to be placed in filePath
    try:
        call('adb pull /sdcard/METER/ ' + filePath, shell=True)
        cmd = 'adb shell ls /sdcard/Meter/'
        s = subprocess.check_output(cmd.split())
        # message("%s"%s)
        call('adb shell rm -rf /sdcard/Meter/*.csv', shell=True)
        call('adb shell rm -rf /sdcard/Meter/*.json', shell=True)
        call('adb shell rm -rf /sdcard/Meter/*.meta', shell=True)
        updateIDfile('0')              # set to 0 to avoid confusion if phone comes on again
        MeterApp.switchForm('MetaForm')
    except:
        message("No device detected")

def data_review():
    MeterApp.switchForm('MetaForm')

def get_time_period(timestr):
    # convert into one of 144 10minute periods of the day
    factors = [6, 0.1, 0.00167]
    return sum([a*b for a, b in zip(factors, map(int, timestr.split(':')))])

def period_hhmm(intPeriod):
    dateTimeValue = datetime.datetime(1,1,1,4,0,0) + datetime.timedelta(minutes = (intPeriod-1) * 10)
    return str(dateTimeValue.time())[0:5]

def next_period(thisTime):
    # advances datetime object by 10 minutes, e.g. '04:50:00' -> '05:00:00'
    return thisTime + datetime.timedelta(minutes = 10)
    
def time_in_seconds(timestr): # not used - just kept for reference...
    # '00:01:01' -> 61
    factors = [3600, 60, 1]
    return sum([a*b for a, b in zip(factors, map(int, timestr.split(':')))])

def getReadingPeriods(_householdID,_condition,_duration):
    # returns start and end of consequitive records matching the condition
    # used to identify how long 'no readings' were taken, or 'high readings'
    metaID = getMetaIDs(_householdID,'E')        # only fetches the first (should only be one...)
    if (metaID != ''):
        sqlq = "SELECT idElectricity FROM Electricity WHERE %s\
                AND Meta_idMeta = %s ORDER BY dt;" % (_condition,metaID)
        eIDs = getSQL(sqlq)
        if eIDs:
            prevID   =  int("%s" % eIDs[0]['idElectricity'])
            startIDs = [prevID]
            endIDs   = []
            durations= []
        
            for eID in eIDs:
                eID = int("%d" % eID['idElectricity'])
                if (eID != (prevID+1)):
                    endIDs.append(prevID)
                    startIDs.append(eID)
                prevID = eID
            endIDs.append(prevID)

            for i in range(len(endIDs)):
                duration = endIDs[i]-startIDs[i]
                if (duration > _duration):
                    durations.append(duration/60)
            if (len(durations) > 5):
                return len(durations)
            else:
                return durations   
        else:
            return "none"
    else:
        return "no meta entry"

def upload_1min_readings(metaIDe):
    # sqlq = "SELECT Meta.idMeta \ From Meta \ Join Household \ On Household.idHOusehold = Meta.Household_idHousehold \ where Household.status >5 AND Household.status < 10 \ AND DataType = 'E' AND Household.Contact_idContact < 5001;"
    # sqlq = "SELECT distinct(Meta_idMeta) FROM Electricity;" # used for initial catchup on all that is in Electricity table

    dbConnection = getConnection()
    sqlq = "select * from Meter.Electricity where Meta_idMeta=%s" % metaIDe
    df_elec       = pd.read_sql(sqlq, con=dbConnection)
    df_elec.index = pd.to_datetime(df_elec.dt)                           # index by time
    df_elec_resampled = df_elec.resample('1min',label='left').median()   # downsample, label left such that time refers to the next minute
    del df_elec_resampled['idElectricity']                               # remove index, so that a new one is auto-incremented
    df_elec_resampled.to_sql(con=dbConnection, name='Electricity_1min', if_exists='append', flavor='mysql') # pandas is brutal, if not append it rewrites the table!!
    # df_elec_resampled.to_csv("%s/el_%s_%s.csv" % (filePath,idMeta[0])) # create a csv copy

def upload_10min_readings(metaIDe):
    dbConnection = getConnection()
    sqlq = "select * from Meter.Electricity_1min where Meta_idMeta=%s" % metaIDe
    df_elec       = pd.read_sql(sqlq, con=dbConnection)
    df_elec.index = pd.to_datetime(df_elec.dt)                           # index by time
    df_elec_resampled = df_elec.resample('10min',label='left').median()   # downsample, label left such that time refers to the next minute
    del df_elec_resampled['idElectricity']                               # remove index, so that a new one is auto-incremented
    df_elec_resampled.to_sql(con=dbConnection, name='Electricity_10min', if_exists='append', flavor='mysql') # pandas is brutal, if not append it rewrites the table!!


def uploadDataFile(fileName,dataType,_metaID,collectionDate):  
    global metaID
    global householdID
    metaID = _metaID

    householdID = getHouseholdForMeta(metaID)
    # this household gets shown on the 'processed' screen
    Screen['7']['Household'] = householdID

    # put file content into database
    dataFile = fileName + '.csv'
    dataFileName = os.path.basename(dataFile)

    if (dataType == 'E'):
        # os.system("scp " + dataFile + " phil@109.74.196.205:/var/lib/mysql-files")

        # XXX makes this the option IF dbHost is localhost
        # sqlq = "LOAD DATA INFILE '" + dataFile + "' INTO TABLE Electricity FIELDS TERMINATED BY ',' (dt,Watt) SET Meta_idMeta = " + str(metaID) + ";"

        os.system("scp " + dataFile + " phil@109.74.196.205:/home/phil/meter")
        sqlq = "LOAD DATA INFILE '/home/phil/meter/" + dataFileName + "' INTO TABLE Electricity FIELDS TERMINATED BY ',' (dt,Watt) SET Meta_idMeta = " + str(metaID) + ";"
        executeSQL(sqlq)
        updateHouseholdStatus(householdID,6)
        upload_1min_readings(metaID)
        upload_10min_readings(metaID)
    elif (dataType == 'A'):
        # handle the xxxx_act.json file
        with open("%s.json"%fileName) as json_data:
             activities = json.load(json_data)
        for activity in activities:
            keyStr = "`, `".join(activities[activity].keys())
            valStr = "', '".join(activities[activity].values())
            sqlq = "INSERT INTO Activities(`%s`) VALUES('%s')"%(keyStr,valStr)
            executeSQL(sqlq)
            collectionDate = activities[activity]['dt_activity'][0:10]

    else:
        csv_data = csv.reader(file(dataFile))
        if (dataType == 'I'):
            sqlq = "INSERT INTO Individual(Meta_idMeta) VALUES('"+str(metaID)+"')"
            individualID = executeSQL(sqlq)                             # create an entry
            commit()
            for row in csv_data:                             # populate columns
                sqlq = "UPDATE Individual SET " + row[1] + " = '" + row[2] + "'\
                        WHERE idIndividual = '"+str(individualID)+"';"
                executeSQL(sqlq)
        if (dataType == 'A'):
            for row in csv_data:                                                       # insert each line into Activities
                sqlq = "INSERT INTO Activities(Meta_idMeta,dt_activity,dt_recorded,tuc,category,activity,location,people,enjoyment,path) \
                        VALUES('"+row[0]+"', '"+row[1]+"', '"+row[2]+"', '"+row[3]+"', '"+row[4]+"', '"+row[5]+"', '"+row[6]+"', '"+row[7]+"', '"+row[8]+"', '"+row[9]+"')"
                executeSQL(sqlq)
    # update meta entry - this MUST already exist!
    # we don't want 'I' in the Meta table - only E or A
    if (dataType == 'I'):
        dataType = 'A'
    sqlq = "UPDATE Meta SET \
            `DataType`='"+ dataType +"' \
            WHERE `idMeta`='" +metaID+"';"
    # 18 Jan 2017 removed `CollectionDate`='"+ collectionDate +"'\
    commit()
    executeSQL(sqlq)
    commit()


def getDeviceCount(householdID):
    # return count of devices configured for this date
    dateChoice = getHHdateChoice(householdID)
    sqlq = "SELECT COUNT(*) FROM Meta WHERE Household_idHousehold = '%s' AND CollectionDate = '%s';" % (householdID,dateChoice)
    result = getSQL(sqlq)[0]
    return result['COUNT(*)']


def getDeviceMetaIDs(householdID):
    # check if eMeter has been configured
    sqlq = "SELECT idMeta, DataType FROM Meta WHERE Household_idHousehold = '%s' ORDER BY Household_idHousehold,DataType;" % householdID
    results = getSQL(sqlq)
    metaIDs = ''
    if (results):
        counter = 0
        for result in results:
            metaIDs = metaIDs + ("{:<6}".format("%s" %  result['idMeta']))
    return metaIDs

def getDevicesReadings(householdID,dateChoice):
    # check if eMeter has been configured
    sqlq = "SELECT idMeta, DataType FROM Meta WHERE Household_idHousehold = '%s' AND CollectionDate = '%s' ORDER BY Household_idHousehold,DataType;" % (householdID,dateChoice)
    results = getSQL(sqlq)
    Counts = ''
    if (results):
        counter = 0
        for result in results:
            if (result['DataType'] == 'E'):
                sqlq = "SELECT COUNT(*) From Electricity_10min WHERE Meta_idMeta = '%s' AND Watt > 20" % result['idMeta']
                c_result = getSQL(sqlq)[0]
                countInt = int(c_result['COUNT(*)']/6.0)
            else:
                sqlq = "SELECT COUNT(*) From Activities WHERE Meta_idMeta = '%s'" % result['idMeta']
                c_result = getSQL(sqlq)[0]
                countInt = c_result['COUNT(*)']
            countStr = "{:<6}".format("%s" %  countInt)
            Counts = Counts + countStr
    return Counts

def getDevicesForDate(householdID,dateChoice):
    # check if eMeter has been configured
    # sqlq = "SELECT idMeta, DataType FROM Meta WHERE Household_idHousehold = '%s' AND CollectionDate = '%s' ORDER BY Household_idHousehold,DataType;" % (householdID,dateChoice)
    sqlq = "SELECT idMeta, DataType FROM Meta WHERE Household_idHousehold = '%s' ORDER BY Household_idHousehold,DataType;" % (householdID)
    results = getSQL(sqlq)
    metaIDs = ''
    if (results):
        counter = 0
        for result in results:
            metaIDs = metaIDs + ("{:<6}".format("%s" %  result['idMeta']))
    return metaIDs

def getDeviceRequirements(householdID):
    # formated list of counters and 'E' for people/eMeter
    counters = getParticipantCount(householdID)
    clist = ''
    for counter in range(counters):
        clist = clist + ("{:<6}".format("A%s" % (counter + 1)))
    clist = clist + ("{:<6}".format("E"))
    return clist

def xgetDeviceMetaIDs(householdID, deviceType):
    # check if eMeter has been configured
    sqlq = "SELECT idMeta FROM Meta WHERE DataType = '%s' AND Household_idHousehold = '%s';" % (deviceType,householdID)
    results = getSQL(sqlq)
    metaIDs = ''
    if (results):
        for result in results:
            metaIDs = metaIDs + ("{:<6}".format("%s" % result['idMeta']))
    return metaIDs

def xgetParticipantCounters(householdID):
    counters = getParticipantCount(householdID)
    clist = ''
    for counter in range(counters):
        clist = clist + ("{:<6}".format("%s:" % (counter + 1)))
    return clist


def getComment(householdID):
    # get the status for this household
    sqlq = "SELECT CONVERT(comment USING utf8) FROM Household WHERE idHousehold = '%s';" % householdID 
    result = getSQL(sqlq)[0]
    CommentStr = "Comment: %s" % result['CONVERT(comment USING utf8)']
    return textwrap.wrap(CommentStr,63)


def getParticipantCount(householdID):
    # get number of diaries required
    sqlq ="SELECT age_group2, age_group3, age_group4, age_group5, age_group6\
            FROM Household \
            WHERE idHousehold = '" + householdID + "';"
    result = getSQL(sqlq)[0]
    return int(result['age_group2']) + int(result['age_group3']) + int(result['age_group4']) + int(result['age_group5']) + int(result['age_group6'])


def updateDataQuality(idMeta,Quality):
    # set Quality in Meta table
    # called when compose_email('graph')
    # XXX add for diaries
    sqlq = "UPDATE Meta \
            SET `Quality`= %s \
            WHERE `idMeta` = %s;" % (Quality,idMeta)
    executeSQL(sqlq)
    commit()

def updateHouseholdStatus(householdID, status):
    # update status of household                            #statusUpdate
    status
    # only case 3,5,6 and 7 dealt with here. others from php forms.
    # 0 : hhq incomplete                hhq.php
    # 1 : hhq complete but no date      hhq.php
    # 2 : date selected                 hhq.php 
    # 3 : 2 week warning sent           compose_email('confirm')
    # 31: delay requested 
    # 4 : date confirmed                confirm.php
    # 5 : kit sent                      device_config()
    # 6 : data uploaded                 uploadDataFile()
    # 7 : data emailed to participant   compose_email('graph')
    # 8 : participant made annotations
    # 10: no el data recorder
    sqlq = "UPDATE Household \
            SET `status`="+ str(status) +"\
            WHERE `idHousehold` ='" + str(householdID) + "';"
    executeSQL(sqlq)
    commit()


def device_config(meterType):
    # 2 Nov 15 - assumes that the apps are already installed
    # global metaID
    global householdID
    # 1) get household ID (assuming a 1:1 relationship!)
    # sqlq = "SELECT idHousehold FROM Household WHERE Contact_idContact = '"\
    #     + str(contactID) + "'"
    # executeSQL(sqlq)
    # householdID = ("%s" % cursor.fetchone())

    # 2) create a meta id entry for an 'eMeter'

    sqlq = "SELECT date_choice FROM Household WHERE idHousehold = '%s'"  %householdID
    result = getSQL(sqlq)[0]
    dateChoice = ("%s" % result['date_choice'])

    sqlq = "INSERT INTO Meta(DataType, Household_idHousehold, CollectionDate) \
           VALUES ('%s', '%s', '%s')" % (meterType,householdID,dateChoice)
    metaID = ("%s" % executeSQL(sqlq))
    commit()
    updateConfigFile(metaID,dateChoice,meterType)

    if (meterType == 'E'):
        updateIDfile(metaID) # XXX currently douplicated with config file - eMeter could use json file, too...
        # only need this once per household
        print_letter('parcel')
        updateHouseholdStatus(householdID,5)
    else:
        # Booklet sticker

        dt   = getHHdtChoice(householdID)
        dt2  = dt + datetime.timedelta(days = 1)
        date = dt.strftime("%-d %b")
        day1 = dt.strftime("%a")
        day2 = dt2.strftime("%a")

        templateText = getTemplate(letterPath + "from_to.md")
        templateText = templateText.replace("[day1]", day1)
        templateText = templateText.replace("[day2]", day2)
        templateText = templateText.replace("[date]", date)
        templateText = templateText.replace("[id]", metaID)

        printSticker(templateText,letterPath + "aMeter")

    MeterApp._Forms['MAIN'].wStatus2.value =\
        "Phone was assigned ID " + metaID
    MeterApp._Forms['MAIN'].wStatus2.display()
    MeterApp._Forms['MAIN'].setMainMenu()

def printSticker(text,fileName):
    myFile = open("%s.md" % (fileName), "w")
    myFile.write(text)
    myFile.close()
    callShell("pandoc -V geometry:paperwidth=8.8cm -V geometry:paperheight=5cm -s %s.md -o %s.pdf" % (fileName,fileName))
    callShell('lp -d MeterLabel -o landscape ' + fileName + '.pdf')


def getDiaryByNumber(number):
    # pick from the list of "A"-type Meta entries for this HH
    sqlq = "SELECT idMeta FROM Meta WHERE DataType = 'A' AND Household_idHousehold = '%s';" % householdID
    results = getSQL(sqlq)

    metaID = "%s" % results[int(number)-1]['idMeta']
    phone_for_paper_diary(metaID)


def phone_for_paper_diary(metaID):
    # the id is typed on command line

    sqlq = "SELECT Household_idHousehold FROM Meta WHERE idMeta = '%s'"  %metaID
    result = getSQL(sqlq)[0]
    householdID = ("%s" % result['Household_idHousehold'])

    sqlq = "SELECT date_choice FROM Household WHERE idHousehold = '%s'"  %householdID
    result = getSQL(sqlq)[0]
    dateChoice = ("%s" % result['date_choice'])
    updateConfigFile(metaID,dateChoice,"P")
    callShell("adb shell am force-stop org.energy_use.meter")

def updateConfigFile(_id,_dateChoice,meterType):
    today = datetime.datetime.now()
    dateFormat        = '%Y-%m-%d'
    dateFormatAndroid = '%Y%m%d'

    dateChoice_dt = datetime.datetime.strptime(_dateChoice,dateFormat)
    if (dateChoice_dt > today):     # only for testing
        dateChoice_dt = today
    startDate = dateChoice_dt.strftime("%Y-%m-%d")
    dateChoice_plus = dateChoice_dt
    dateChoice_plus += datetime.timedelta(days=1)
    endDate   = dateChoice_plus.strftime("%Y-%m-%d")
    jstring = {"id": _id}
    jstring.update({"start": "%s" %startDate})
    jstring.update({"end": "%s" %endDate})  # XXX needs date + 1 Day
    times1 = [
            "17:30:00",
            "18:00:00",
            "18:30:00"]
    times2 = [
            "08:00:00",
            "08:30:00",
            "17:30:00",
            "18:00:00",
            "18:30:00"]
    dts = []
    for time in times1:
        dts.append("%s %s" %(jstring['start'],time))
    for time in times2:
        dts.append("%s %s" %(jstring['end'],time))
    if (meterType == "P"):
        # device for manual entry of paper diary
        # needs no reminders
        jstring.update({"times": []})
        # set device time to the day of recording
        dateChoice_dt += datetime.timedelta(hours=17)
        startDateAdb = dateChoice_dt.strftime("%m%d%H%M%Y.%S")
        callShell("adb root")
        callShell("adb shell \"date %s\"" % startDateAdb)
    else:
        jstring.update({"times": dts})
        callShell("adb root")
        callShell('adb shell "date `date +%m%d%H%M%Y.%S`"')
    config_file = open(configFilePath, "w")
    config_file.write(json.dumps(jstring, indent=4, separators=(',', ': ')))
    config_file.close()
    callShell('adb shell "mkdir /sdcard/METER/"')
    callShell('adb push ' + configFilePath + ' /sdcard/METER/')
    callShell('adb shell am force-stop org.energy_use.meter')
    callShell('adb install -r ./apk/aMeter.apk')


def updateIDfile(_id):
    idFile = open(idFilePath, 'w+')
    idFile.write(str(_id))
    idFile.close()
    # XXX only needs doing once, but flashing doesn't seem to create this folder
    callShell('adb shell mkdir /sdcard/METER')
    callShell('adb push ' + idFilePath + ' /sdcard/METER/')
    ## Android 6 (Pixi4) requires:
    # adb shell "date `date +%m%d%H%M%Y.%S`"
    callShell('adb shell date -s `date "+%Y%m%d.%H%M%S"`')
    # shut down phone (unless id is 0)
    if (_id != '0'):
        callShell('adb shell reboot -p')


def setSerialNumber(SerialNumber):
    # command typed number is set as serial number for current metaID
    metaID = getMetaIDs(householdID,'E')
    sqlq = "UPDATE Meta \
            SET SerialNumber = '%s'\
            WHERE idMeta = '%s'" % (SerialNumber,metaID)
    executeSQL(sqlq)
    commit()



def aMeter_setup():
    # compile and upload the cordova activity app
    callShell('/Users/phil/Sites/MeterApp/platforms/android/cordova/run')
    # install AutoStart app
    callShell('adb install ~/Software/Android/AutoStart_2.1.apk')

def root_phone():
    callShell('adb install -r ./apk/root.apk')
    # callShell('adb install -r ./apk/Insecure.apk')
    # to configure a phone, install insecure and tick the two boxes to root at start
    callShell('adb install -r ./apk/Flashify.apk')
    callShell('adb push ./apk/recovery.img /sdcard/')
    message("Complete process\n\
            1) connect to WiFi\n\
            2) run KingoRoot\n\
            3) Flashify > Recovery image > choose a file \"/sdcard/recovery.img\" >yup (2min)\n\
            4) <OK> this message to flash\n\)")
    flash_phone("E")

def flash_phone(meterType):
    # restore phone from Master copy
    if (meterType == 'E'):
        callShell('adb push ./flash_eMeter/TWRP/ /sdcard/')
    elif (meterType == 'A'):
        callShell('adb push ./flash_aMeter/TWRP/ /sdcard/')
    callShell('adb reboot recovery')
    message("Phone restarting\n\
            1) Restore \n\
            2) Select \"... KitKat\" swipe (2min) \n\
            3) Reboot System\n\
            4) Reconnect USB (!)\n\
            5) <OK> this message to configure ID")
    updateIDfile('0')

def eMeter_setup():
    # superseeded by flash_phone()
    # Compile and run device_config(E)
    # XXX call('ant debug -f ~/Software/Android/DMon/build.xml', shell=True)
    # remove old copy
    # XXX call('adb uninstall com.Phil.DEMon', shell=True)
    # install new
    # call('adb install -r \
    #     ~/Software/Android/DMon/bin/MainActivity-debug.apk',
    #      shell=True)
    # install AutoStart app
    call('adb install -r ./apk/AppHider.apk',  shell=True)
    call('adb install -r ./apk/AutoStart.apk',  shell=True)
    call('adb install -r ./apk/eMeter.apk',  shell=True)

    # create the METER folder
    call('adb shell mkdir /sdcard/METER', shell=True)
    # configure phone for recording
    device_config('E')

def getMetaIDs(hhID, deviceType):
    # check if eMeter has been configured
    sqlq = "SELECT idMeta FROM Meta WHERE DataType = '%s' AND Household_idHousehold = '%s';" % (deviceType,hhID)
    result = getSQL(sqlq)
    if (result):
        return ("%s" % result[0]['idMeta'])
    else:
        return ''

def getHHdateChoice(hhID):
    # reads a sql date in format "2016-12-31"
    sqlq = "SELECT date_choice FROM Household WHERE idHousehold = '%s';" % hhID
    result = getSQL(sqlq)[0]
    dateStr = ("%s" % result['date_choice'])
    return dateStr

def getHHdtChoice(hhID):
    # reads a sql date in format "2016-12-31" and returns datetime object
    sqlq = "SELECT date_choice FROM Household WHERE idHousehold = '%s';" % hhID
    result = getSQL(sqlq)[0]
    dateStr = ("%s" % result['date_choice'])
    if (dateStr != 'None'):
        f = '%Y-%m-%d'
        return datetime.datetime.strptime(dateStr, f)
    else:
        return "None"

def getDateChoice(hhID):
    # return collection date as a string: "Sun, 31 Dec"
    this_dt = getHHdtChoice(hhID)
    if (this_dt != 'None'):
        return this_dt.strftime("%a, %-d %b")
    else:
        return "None"

def getDateTimeFormated(dts):
    # DateTimeString as received from database: return 31 Jan 16
    # http://strftime.org/
    if (dts != 'None'):
        f = '%Y-%m-%d %H:%M:%S'
        this_dt = datetime.datetime.strptime(dts, f)
        return this_dt.strftime("%-d %b %y")
    else:
        return "None"

def compose_email(type,edit=True):
    # Contact participant with editabel email
    # edit = False -> send immediately
    global householdID
    # get contact details
    contactID = getContact(householdID)
    metaID    = getMetaIDs(householdID,'E')
    sqlq = "SELECT Name, Surname, Address1,Address2,Town,Postcode,email \
            FROM Contact \
            WHERE idContact = '%s';" % contactID
    result = getSQL(sqlq)[0]
    
    thisName    = ("%s %s" % (result['Name'], result['Surname']))
    thisAddress = ("%s</br>%s</br>%s %s" % (result['Address1'],result['Address2'],result['Town'],result['Postcode']))
    thisAddress = thisAddress.replace("None </br>", "")
    thisDate    = getDateChoice(householdID)
    thisEmail   = ("%s" % (result['email']))
    CcEmail     = 'philipp.grunewald@ouce.ox.ac.uk'
    thisAddress = thisAddress.replace("None</br>", "")
    participantCount = ("%s" % getParticipantCount(str(householdID)))
    # prepare the custom email
    # templateFile = open(emailPath + "email_compose_" + type + ".md", "r")
    templateFile = open(emailPath + "email_" + type + ".html", "r")
    templateText = templateFile.read()
    templateFile.close()
    templateText = templateText.replace("[householdID]", householdID)
    templateText = templateText.replace("[name]", thisName)
    templateText = templateText.replace("[address]", thisAddress)
    templateText = templateText.replace("[date]", thisDate)
    templateText = templateText.replace("[metaID]", metaID)
    templateText = templateText.replace("[securityCode]", getSecurityCode(householdID))
    templateText = templateText.replace("[participantCount]", participantCount)
    if (participantCount != "1"):
        templateText = templateText.replace("[s]", "s")
        templateText = templateText.replace("[ies]", "ies")
        templateText = templateText.replace("[people]", "people")
        templateText = templateText.replace("{multiple booklets}", ". Each of you is encouraged to take part (so long as they are eight or older). I hope you will be able to persuade them to join you")
    else:
        templateText = templateText.replace("[s]", "")
        templateText = templateText.replace("[ies]", "y")
        templateText = templateText.replace("[people]", "person")
        templateText = templateText.replace("{multiple booklets}", "") 

    if (edit):
        # needs email in line 1, Cc in line 2 and Subject in line 3
        # template has subject as line one -> insert emails
        templateText = thisEmail + '\n' + CcEmail + '\n' + templateText
    else:
        # only keep the body of the text -> remove line 1 (Subject)
        subjectLine = templateText.splitlines()[0]
        templateText = templateText[templateText.find('\n')+1:]     # find line break and return all from there - i.e. remove first line

    emailFilePath = emailPath + "tempEmail.htmail"
    emailFile = open(emailFilePath, "w+")
    emailFile.write(templateText)
    emailFile.close()

    if (type == 'confirm'):
        updateHouseholdStatus(householdID, 3)
    elif (type == 'reschedule'):
        # I asked for a new date
        updateHouseholdStatus(householdID, 31)
    elif (type == 'graph'):
        # households that had been 'processed' and now 'processed and contacted'
        updateHouseholdStatus(householdID, 7)
        updateDataQuality(metaID,1)
    elif (type == 'fail'):
        updateHouseholdStatus(householdID, 10)
        updateDataQuality(metaID,0)

    
    if (edit):
        call('vim ' + emailFilePath, shell=True)
        MeterApp._Forms['MAIN'].wMain.display() # XXX does not have the desired effect of removing the light 'vim' background
    else:
        call('mutt -e "set content_type=text/html" -s "' + subjectLine + '" ' + thisEmail + ' -b philipp.grunewald@ouce.ox.ac.uk < ' + emailFilePath, shell=True)
    # 29 Jan 2017 added to redraw screen after mailing
    MeterApp._Forms['MAIN'].setMainMenu()

def email_many():
    # compose message
    emailFilePath = emailPath + "email_many.html"
    # give oportunity to edit the template
    call('vim ' + emailFilePath, shell=True)

    templateFile = open(emailFilePath, "r")
    templateText = templateFile.read()
    templateFile.close()

    subjectLine = templateText.splitlines()[0]
    templateText = templateText[templateText.find('\n')+1:]     # find line break and return all from there - i.e. remove first line

    # personalise
    emailPathPersonal = emailPath + "email_personal.html"
    sqlq="SELECT Name,email FROM Mailinglist WHERE scope = 'test'"
    results = getSQL(sqlq)
    for result in results:
        emailText = templateText.replace("[name]", result['Name'])
        emailAddress = result['email']
        emailFile = open(emailPathPersonal, "w+")
        emailFile.write(emailText)
        emailFile.close()
        call('mutt -e "set content_type=text/html" -s "' + subjectLine + '" ' + emailAddress + ' < ' + emailPathPersonal, shell=True)

def getTemplate(fileName):
    templateFile = open(fileName, "r")
    templateText = templateFile.read()
    templateFile.close()
    return templateText


def print_letter(letterType):
    # personal letter as pdf
    global householdID
    contactID = getContact(householdID)
    participantCount = ("%s" % getParticipantCount(str(householdID)))

    # The letter
    dateToday = datetime.datetime.now()
    todayDate = dateToday.strftime("%e %B %Y")

    sqlq = "SELECT Name, Surname, Address1,Address2,Town,Postcode FROM Contact WHERE idContact = '%s';" % contactID
    result = getSQL(sqlq)[0]
    thisName    = ("%s %s" % (result['Name'],result['Surname']))
    thisAddress = ("%s\n\n%s\n\n%s %s" % (result['Address1'],result['Address2'],result['Town'],result['Postcode']))
    thisAddress = thisAddress.replace("None\n\n", "")

    dt   = getHHdtChoice(householdID)
    dt2  = dt + datetime.timedelta(days = 1)
    date = dt.strftime("%-d %b")
    weekday = dt.strftime("%A")
    nextday = dt2.strftime("%A")

    if (letterType == "chase_eMeter"):
        templateText = getTemplate(letterPath + "letter_chase_eMeter.md")
    else:
        templateText = getTemplate(letterPath + "letter_narrow.md")
    templateText = templateText.replace("[address]", thisAddress)
    templateText = templateText.replace("[name]", thisName)
    templateText = templateText.replace("[today]", todayDate)
    templateText = templateText.replace("[date]", "%s" % date)
    templateText = templateText.replace("[weekday]", "%s" % weekday)
    templateText = templateText.replace("[nextday]", "%s" % nextday)
    templateText = templateText.replace("[participantCount]", participantCount)

    if (participantCount != "1"):
        templateText = templateText.replace("[s]", "s")
        templateText = templateText.replace("{multiple booklets}", " -- to help you identify them there are numbers on the back (1 for the oldest, 2 second oldest...). Do encourage the others to join you. The more people contribute, the better our understanding of electricity use becomes")
    else:
        templateText = templateText.replace("[s]", "")
        templateText = templateText.replace("{multiple booklets}", "") 

    myFile = open(letterPath + "temp_letter.md", "w+")
    myFile.write(templateText)
    myFile.close()

    letterFile = letterPath + contactID + "_letter"

    call('pandoc  --variable classoption=twocolumn -V geometry:margin=0.6in -V fontsize=11pt -s ' + letterPath + "temp_letter.md -o" + letterFile + ".pdf", shell=True)
    call('lp -d Xerox_Phaser_3250 ' + letterFile + '.pdf', shell=True)

    # ADDRESS LABEL
    # produces postage label and personal letter

    address = getTemplate(letterPath + "_address.md")
    address = address.replace("[Name]",      thisName)
    address = address.replace("[Address1]", "%s" % result['Address1'])
    address = address.replace("[Address2]", "%s" % result['Address2'])
    address = address.replace("[Town]",     "%s" % result['Town'])
    address = address.replace("[Postcode]", "%s" % result['Postcode'])
    address = address.replace("None", "")

    printSticker(address,letterPath + "address")

# ------------------------------------------------------------------------------
# --------------------------FORMS-----------------------------------------------
# ------------------------------------------------------------------------------

class ActionControllerData(nps.MultiLineAction):
    # action key shortcuts                                      #action_keys
    def __init__(self, *args, **keywords):
        super(ActionControllerData, self).__init__(*args, **keywords)
        global MasterKeys
        MasterKeys = {
                '0': self.SwitchScreen,
                'q': self.show_MainMenu,
                'Q': self.parent.exit_application,
                'P': data_download,
                }
        global MasterKeysLabels
        MasterKeysLabels = {
                '0': ' Home',
                'q': ' Back',
                'Q': 'uit',
                'P': 'rocess',
                }
        self.add_handlers(MasterKeys)

        # global MenuActionKeys
        # MenuActionKeys = {
        #     # '1': self.eMeter_setup,
        #     #   'p': self.eMeter_setup,
        #     # 'A': print_letter,
        #     'A': self.btnA,
        #     'B': self.btnB,
        #     ## 'A': self_pre_post_email,
        #     'D': self.aMeter_id_setup,
        #     'E': self.btnE,
        #     '>': getNextHousehold,
        #     '<': getPreviousHousehold,

        #     '0': self.SwitchScreen,
        #     '1': self.SwitchScreen,
        #     '2': self.SwitchScreen,
        #     '3': self.SwitchScreen,
        #     # '1': self.Screen1,
        #     # '2': self.Screen2,
        #     # '3': self.Screen3,
        #     # '4': self.Screen4,
        #     # '5': self.Screen5,

        #     'P': self.btnP,
        #     # 'P': self.data_download,
        #     # 'S': self.showHouseholds,
        #     # "M": toggleScreenKey,
        #     "q": self.show_MainMenu,
        #     "Q": self.parent.exit_application,
        #     # "t": self.show_DataTypes,
        #     # "c": self.show_Contact,
        #     # "a": self.show_NewContact,
        #     # "I": self.show_Individual,
        #     # "m": self.show_MetaForm,
        #     # "s": self.show_MainMenu,
        # }
        # message("%s"% self.add_handlers)
        # self.add_handlers(MenuActionKeys)


    def actionHighlighted(self, selectedLine, keypress):
        # choose action based on the display status and selected line           #action_highlighted
        global householdID 

        if (self.parent.myStatus == 'Main'):
            self.parent.wMain.values = ['Selection: ', selectedLine,
                                        '\tM\t\t to return to the main menu']
            self.parent.wMain.display()
            global ActionKeys
            ActionKeys[selectedLine[1]]()

        elif (self.parent.myStatus == 'Contact'):
            dataArray = selectedLine.split('\t')
            householdID = getHouseholdForContact(str(dataArray[0]))
            message("Waring:\nThere may be other Household entries for this Contact")
            # contactID = str(dataArray[0])
            self.parent.wStatus2.value =\
                "Contact changed to " + str(dataArray[1])
            self.parent.setMainMenu()

        elif (self.parent.myStatus == 'Households'):
            # items are padded out with spaces to produce neat columns. These are removed with .strip()
            dataArray   = selectedLine.split('\t')
            householdID = str(dataArray[0]).strip()
            self.parent.wStatus2.value =\
                "Household changed to " + householdID
            self.parent.wStatus2.display()
            self.parent.setMainMenu()


        elif (self.parent.myStatus == 'Meta'):
            dataArray = selectedLine.split('\t\t')
            global metaID
            metaID  = str(dataArray[0])
            dataType = str(dataArray[3])
            self.parent.wStatus2.value =\
                "Meta " + metaID + ", type " + dataType
            self.parent.wStatus2.display()
            self.parent.setMainMenu()

        elif (self.parent.myStatus == 'Household'):
            dataArray = selectedLine.split('\t')
            householdID  = str(dataArray[0])
            self.parent.wStatus2.value =\
                "Household changed to " + str(dataArray[0])
            self.parent.wStatus2.display()
            self.parent.setMainMenu()

        elif (self.parent.myStatus == 'Individual'):
            dataArray = selectedLine.split('\t')
            individual  = str(dataArray[0])
            self.parent.wStatus2.value =\
                "Individual changed to " + str(dataArray[2]) + " from household " + str(dataArray[0])
            self.parent.wStatus2.display()
            self.parent.setMainMenu()

        elif (self.parent.myStatus == 'Tables'):
            self.parent.wStatus2.values = ['Table ', selectedLine, 'was selected!']
            self.parent.wStatus2.display()
            self.parent.display_selected_data(selectedLine)

        else:
            # check if command key is present in format [x]
            Key = selectedLine.split('[')[1]
            try:
                ActionKeys[Key[0]](ord(Key[0]))
            except:
                message("No action for %s defined" % Key[0])


    def mute(self, *args):
        pass

    def updateActionKeys(self,ScreenKey):
        # redefine what keys do
        global ActionKeys
        for key in ActionKeys:
            # make all 'old' Action keys 'mute'
            ActionKeys[key] = self.mute
        for ScreenNumber in Screen:
            # Screen keys (0-n) always work
            ActionKeys[ScreenNumber] = self.SwitchScreen
        for ActionKey in Screen[ScreenKey]['Actions']:
            # Actions specific to this screen
            ActionKeys[ActionKey] = Screen[ScreenKey]['Actions'][ActionKey]['Action']
        self.add_handlers(ActionKeys)

    def SwitchScreen(self, *args, **keywords):
        # convert key number to character (48 -> '0')
        Key = chr(args[0])
        self.updateActionKeys("%s"%Key)
        showScreen(Key)

    def show_MainMenu(self, *args, **keywords):
        self.parent.setMainMenu()

    def aMeter_id_setup(self, *args, **keywords):
        device_config('A')
        
    def showHouseholds(self, *args, **keywords):
        self.parent.display_selected_data('Households')

    def data_download(self, *args, **keywords):
        data_download()



    def show_Contact(self, *args, **keywords):
        self.parent.myStatus = 'Contact'
        self.parent.display_selected_data("Contact")

    def show_Individual(self, *args, **keywords):
        self.parent.myStatus = 'Individual'
        self.parent.display_selected_data("Individual")

    def show_MetaForm(self, *args, **keywords):
        self.parent.parentApp.switchForm('MetaForm')

    def show_EditContact(self, *args, **keywords):
        self.parent.parentApp.switchForm('EditContact')

    def show_EditHousehold(self, *args, **keywords):
        self.parent.parentApp.switchForm('EditHousehold')

    def show_NewContact(self, *args, **keywords):
        self.parent.parentApp.switchForm('NewContact')

    def formated_data_type(self, vl):
        return "%s (%s)" % (vl[1], str(vl[0]))

    def formated_word(self, vl):
        return "%s" % (vl[0])


class ActionControllerSearch(nps.ActionControllerSimple):
    def create(self):
        self.add_action('^/.*', self.set_search, True)
        self.add_action('^:\d.*', self.set_serialNumber, False)
        self.add_action('^:d\d\d\d\d', self.paperDiary, False)
        self.add_action('^:c\d\d', self.setContact, False)
        self.add_action('^:h\d', self.setHousehold, False)
        self.add_action('^:m\d', self.setMetaID, False)
        self.add_action('^:d\d$', self.paperDiaryNumber, False)

    def set_search(self, command_line, widget_proxy, live):
        self.parent.value.set_filter(command_line[1:])
        self.parent.wMain.values = self.parent.value.get()
        self.parent.wMain.display()

    def setHousehold(self, command_line, widget_proxy, live): # entered as 4 digit
        if (householdExists(command_line[2:])):
            global householdID
            householdID = command_line[2:]
            self.parent.setMainMenu()
        else:
            message("No household ID=%s found"%command_line[2:])

    def setContact(self, command_line, widget_proxy, live): # entered as 4 digit
        global householdID
        householdID = getHouseholdForContact(command_line[2:])
        self.parent.setMainMenu()

    def setMetaID(self, command_line, widget_proxy, live): # entered as 4 digit
        global householdID
        householdID = getHouseholdForMeta(command_line[2:])
        self.parent.setMainMenu()

    def paperDiary(self, command_line, widget_proxy, live): # entered as 4 digit
        phone_for_paper_diary(command_line[2:])

    def paperDiaryNumber(self, command_line, widget_proxy, live): # entered as single digit (for current HH)
        getDiaryByNumber(command_line[2:])

    def set_serialNumber(self, command_line, widget_proxy, live): # just for testing
        setSerialNumber(command_line[1:])


    # NEEDED???
    def setMainMenu(self, command_line, widget_proxy, live):
        self.parent.setMainMenu()


class MeterMain(nps.FormMuttActiveTraditionalWithMenus):
    ACTION_CONTROLLER = ActionControllerSearch
    MAIN_WIDGET_CLASS = ActionControllerData
    # myStatus = Screen[str(ScreenKey)]['Name']
    myStatus = "Welcome to the Meter Interface"


    global cursor
    cursor = connectDatabaseOLD(dbHost)

    def beforeEditing(self):
        # connect/reconnect
        global cursor
        cursor = connectDatabase(dbHost)


        global first_time
        if first_time:
            first_time = False
            self.initialise()
            # load Screen
            global Screen
            Screen = self.getScreens()

        # global ScreenKey
        # mainScreenText = self.getMenuText()
        # self.value.set_values(mainScreenText)


        showScreen(ScreenKey)


        self.wStatus1.value = "METER " + self.myStatus
        self.wMain.values = self.value.get()
        self.wMain.display()

    def initialise(self):
        # menu and sub-menues           #menu_bar

        # global dataType
        self.m1 = self.add_menu(name="Data handling", shortcut="D")
        self.m1.addItemsFromList([
            ("Download from phone", data_download, "d"),
            ("Review Meta Data", data_review, "r"),
        ])
        self.m2 = self.add_menu(name="Setup a batch", shortcut="B")
        self.m2.addItem(text='Show Households', onSelect=MeterApp._Forms['MAIN'].display_selected_data, shortcut='S', arguments=['Households'])
        self.m2.addItem(text='eMeter ID', onSelect=device_config, shortcut='e', arguments='E')
        self.m2.addItem(text='aMeter ID', onSelect=device_config, shortcut='a', arguments='A')
        self.m2.addItem(text='aMeter for Paper Diary', onSelect=device_config, shortcut='p', arguments='P')
        # self.m2.addItem(text='eMeter apk', onSelect=eMeter_setup, shortcut='E', arguments=None)
        self.m2.addItem(text='Flash eMeter', onSelect=flash_phone, shortcut='E', arguments='E')
        self.m2.addItem(text='Flash aMeter', onSelect=flash_phone, shortcut='A', arguments='A')
        self.m2.addItem(text='aMeter app upload', onSelect=aMeter_setup, shortcut='C', arguments=None)
        self.m2.addItem(text='Root phone', onSelect=root_phone, shortcut='R', arguments=None)

        self.m2 = self.add_menu(name="Work with data", shortcut="i")

        self.m2 = self.add_menu(name="Emails", shortcut="e")
        self.m2.addItem(text='Email many', onSelect=email_many, shortcut='m', arguments=None)
        self.m2.addItem(text='Email blank', onSelect=compose_email, shortcut='b', arguments=['blank'])
        self.m2.addItem(text='Date reschedule', onSelect=compose_email, shortcut='d', arguments=['reschedule'])
        self.m2.addItem(text='Email confirm date', onSelect=compose_email, shortcut='c', arguments=['confirm'])
        self.m2.addItem(text='Email pack sent', onSelect=compose_email, shortcut='p', arguments=['parcel'])
        self.m2.addItem(text='Email graph', onSelect=compose_email, shortcut='g', arguments=['graph'])
        self.m2.addItem(text='Email on failure', onSelect=compose_email, shortcut='f', arguments=['fail'])
        self.m2.addItem(text='Request return', onSelect=compose_email, shortcut='r', arguments=['request_return'])

        self.m2.addItem(text='------No editing------', onSelect=self.IgnoreForNow, shortcut='', arguments=None)
        self.m2.addItem(text='Email blank', onSelect=compose_email, shortcut='B', arguments=['blank',False])
        self.m2.addItem(text='Email confirm date', onSelect=compose_email, shortcut='C', arguments=['confirm',False])
        self.m2.addItem(text='Email pack sent', onSelect=compose_email, shortcut='P', arguments=['parcel',False])
        self.m2.addItem(text='Email graph', onSelect=compose_email, shortcut='G', arguments=['graph',False])
        self.m2.addItem(text='Email on failure', onSelect=compose_email, shortcut='F', arguments=['fail',False])

        self.m2 = self.add_menu(name="Database management", shortcut="m")
        self.m2.addItem(text='Show tables', onSelect=self.show_Tables, shortcut='t')
        self.m2.addItem(text='Select contact', onSelect=self.list_contacts, shortcut='c')
        self.m2.addItem(text='Edit contact', onSelect=self.show_EditContact, shortcut='C')
        self.m2.addItem(text='Edit household', onSelect=self.show_EditHousehold, shortcut='H')
        self.m2.addItem(text='New    contact', onSelect=self.add_contact, shortcut='n')
        self.m2.addItem(text='Select meta', onSelect=self.list_meta, shortcut='m')
        self.m2.addItem(text='Change database', onSelect=self.toggleDatabase, shortcut='d')
        self.m2.addItem(text='Backup database', onSelect=backup_database, shortcut='b')

        self.m3 = self.add_menu(name="Exit", shortcut="X")
        self.m3.addItem(text="Home", onSelect = MeterApp._Forms['MAIN'].setMainMenu,shortcut="h")
        self.m3.addItem(text="Exit", onSelect = self.exit_application, shortcut="X")

    def getMenuText(self):
        #menu_text

        if (householdID != '0'):
            # a hh is assigned
            Screen[ScreenKey]['Index'] = int(self.getHHindex(householdID))
        else:
            # get the 1st in the list
            Screen[ScreenKey]['Index'] = 1
            self.getHH()

        contactID   = getContact(householdID)

        MenuText = []
        line     = "\t\t\t|_______________________________________|"
        longline = "\t\t\t|_________________________________________________________________|"

        if (Screen[ScreenKey]['Name'] == 'Home'):
            # HOME Screen
            # Show METER logo
            for logoLine in open("meterLogo.txt", "r"):
                MenuText.append("\t" + logoLine)
            MenuText.append("\n")

            # Show screen options
            MenuText.append("\t\t\t _Screen options________________________")  
            for key in sorted(Screen):
                # display all screens
                MenuText.append(formatBox("[%s] %s:" % (key,Screen[key]['Name']), "(%s)" % (getHouseholdCount(Screen[key]['Criterium']))))
            MenuText.append(line)
            MenuText.append("\n")

        if (Screen[ScreenKey]['Actions']):
            # Show keys available
            MenuText.append("\n")
            MenuText.append("\t\t\t _Commands______________________________")  
            # MenuText.append (formatBox("",""))
            for ActionKey in sorted(Screen[ScreenKey]['Actions']):
                # show avalable commands
                MenuText.append (formatBox("[%s] %s" % (ActionKey, Screen[ScreenKey]['Actions'][ActionKey]['Label']),''))
            MenuText.append(line)
            MenuText.append("\n")

        MenuText.append("\n")

        if (householdID != "0"):
            # Show Household information
            MenuText.append( "\t\t\t _Household information  (%3s/%3s) _______________________________"% (Screen[ScreenKey]['Index'], getHouseholdCount(Screen[ScreenKey]['Criterium'])))
            MenuText.append(formatBigBox("Contact:",  getNameOfContact(contactID) + ' (' + contactID + ')'))
            line
            status = getStatus(householdID)
            date   = getDateChoice(householdID)
            dt_date= getHHdateChoice(householdID)
            MenuText.append(formatBigBox("Date:", date))
            MenuText.append(formatBigBox("Household:", householdID))
            MenuText.append(formatBigBox("Status:", status))
            MenuText.append(formatBigBox("People:", getDeviceRequirements(householdID)))
            # MenuText.append(formatBigBox("Devices:", getDeviceMetaIDs(householdID)))
            MenuText.append(formatBigBox("Devices:", getDevicesForDate(householdID,dt_date)))
            MenuText.append(formatBigBox("Readings:", getDevicesReadings(householdID,dt_date)))
            if (status > 5):
                MenuText.append(formatBigBox("Low:",  getReadingPeriods(householdID,Criteria['no reading'],60))) # last parameter is min duration to report
                MenuText.append(formatBigBox("High:", getReadingPeriods(householdID,Criteria['high reading'],60))) # last parameter is min duration to report
            MenuText.extend(formatBoxList(getComment(householdID)))
            MenuText.append(longline)
        MenuText.append("\n")
        return MenuText

    def email(self,key):
        # compose_email(Screen[ScreenKey][chr(key)['EmailType'])
        compose_email(Screen[ScreenKey]['Actions'][chr(key)]['arguments'])

    def showHouseholds(self,key):
        self.display_selected_data('Households')

    def deviceConfig(self,key):
        deviceCount = int(getDeviceCount(householdID))
        participantCount = int(getParticipantCount(householdID))
        if (deviceCount < participantCount):
            device_config('A')
        elif (deviceCount == participantCount):
            device_config('E')
        else:
            message("All devices are configured (or should be :-)")
        # recount after new device configured
        deviceCount = getDeviceCount(householdID)
        if (deviceCount < participantCount):
            Screen['4']['Actions']['D']['Label'] = "Configure A%s"% (deviceCount+1)
        else:
            Screen['4']['Actions']['D']['Label'] = "Configure eMeter"


    def getHHindex(self,HouseholdID):
        # find at what position in the list the current hh is
        sqlq = "SELECT rank \
                FROM ( \
                    SELECT idHousehold, date_choice,\
                    @rownum := @rownum + 1 AS rank\
                        FROM Household, (SELECT @rownum := 0) r\
                        WHERE %s \
                    ) `selection` WHERE idHousehold = %s" % (Screen[ScreenKey]['Criterium'],HouseholdID)
        if (getSQL(sqlq)):
            result = getSQL(sqlq)[0]
            return ("%d" % int(result['rank']))
        else:
            return 0

    def nextHH(self,key):
        # get the next hh matching the modus criteria
        global Screen
        Screen[ScreenKey]['Index'] += 1
        self.getHH()
        self.setMainMenu()


    def prevHH(self,key):
        # get the next hh matching the modus criteria
        global Screen
        if (Screen[ScreenKey]['Index'] > 1):
            Screen[ScreenKey]['Index'] -= 1
        self.getHH()
        self.setMainMenu()

    def getHH(self):
        # set householdID to indexed household and show
        global householdID
        sqlq = "SELECT idHousehold FROM Household WHERE %s LIMIT %s,1;" % (Screen[ScreenKey]['Criterium'],Screen[ScreenKey]['Index']-1)
        try:
            result = getSQL(sqlq)[0]
            householdID =  ("%s" % result['idHousehold'])
        except:
            householdID = '0'



    def getScreens(self):
        Screen = {
            '0': {
                'Name'      : 'Home',
                'Criterium': 'status >=0',
                'Household': '0',
                'Actions': {
                    }
                },
            '1': {
                'Name':     'No date yet',
                'Criterium': 'date_choice < "2010-01-01"',
                'Household': '0',
                'Index'    :  0,
                'Actions': {
                        'E': {
                            'Action': self.email,
                            'arguments': 'date',
                            'Label': "Email dates"
                            },
                        'S': {
                            'Action': self.showHouseholds,
                            'Label': "Select"
                            },
                        '<': {
                            'Action': self.prevHH,
                            'Label': "Prev"
                            },
                        '>': {
                            'Action': self.nextHH,
                            'Label': "Next"
                            },
                    }
                },
            '2':   {
                'Name'     : 'Future',
                'Criterium': 'date_choice > CURDATE()',
                'Household': '0',
                'Actions': {
                        'E': {
                            'Action': self.email,
                            'arguments': 'date',
                            'Label': "Email alternative dates"
                            },
                        'S': {
                            'Action': self.showHouseholds,
                            'Label': "Select"
                            },
                        '<': {
                            'Action': self.prevHH,
                            'Label': "Prev"
                            },
                        '>': {
                            'Action': self.nextHH,
                            'Label': "Next"
                            },
                    }
                },
            '3': {
                'Name'     : 'Upcoming',
                'Criterium':    'status < 4 AND date_choice >= CURDATE() AND date_choice < CURDATE() + INTERVAL "21" DAY ORDER BY date_choice ASC',
                'Household': '0',
                'Actions': {
                        'E': {
                            'Action'    : self.email,
                            'arguments' : 'confirm',
                            'Label'     : "Email to confirm"
                            },
                        'S': {
                            'Action': self.showHouseholds,
                            'Label': "Select"
                            },
                        '<': {
                            'Action': self.prevHH,
                            'Label': "Prev"
                            },
                        '>': {
                            'Action': self.nextHH,
                            'Label': "Next"
                            },
                    }
                 },
            '4': {
                'Name'      : 'Confirmed',
                 'Criterium':    'status = 4 ORDER BY date_choice,idHousehold ASC',
                 'Household': '0',
                 'Actions': {
                        'D': {
                            'Action': self.deviceConfig,
                            'Label': "Device config"
                            },
                        'E': {
                            'Action'    : self.email,
                            'arguments' : 'sent',
                            'Label'     : "Email parcel sent"
                            },
                        'S': {
                            'Action': self.showHouseholds,
                            'Label': "Select Household"
                            },
                        '<': {
                            'Action': self.prevHH,
                            'Label': "Prev"
                            },
                        '>': {
                            'Action': self.nextHH,
                            'Label': "Next"
                            },
                    }
                 },
             '5': {
                'Name'      : 'Issued',
                 'Criterium': 'status = 5 ORDER BY date_choice ASC',
                 'Email':     'request_return',
                 'Household': '0',
                 'Actions': {
                        'E': {
                            'Action': self.email,
                            'Label': "Email dates"
                            },
                        'S': {
                            'Action': self.showHouseholds,
                            'Label': "Select"
                            },
                        '<': {
                            'Action': self.prevHH,
                            'Label': "Prev"
                            },
                        '>': {
                            'Action': self.nextHH,
                            'Label': "Next"
                            },
                    }
                 },
             '6': {
                'Name'      : 'Overdue',
                 'Criterium': 'status = 5 AND date_choice < CURDATE() - INTERVAL "21" DAY ORDER BY date_choice ASC',
                 'Household': '0',
                 'Actions': {
                        'E': {
                            'Action': self.email,
                            'arguments': 'request_return',
                            'Label': "Email dates"
                            },
                        'S': {
                            'Action': self.showHouseholds,
                            'Label': "Select"
                            },
                        '<': {
                            'Action': self.prevHH,
                            'Label': "Prev"
                            },
                        '>': {
                            'Action': self.nextHH,
                            'Label': "Next"
                            },
                    }
                 },
             '7': {
                'Name'      : 'Processed',
                 'Criterium': 'status > 5 ORDER BY date_choice DESC',
                 'Household': '0',
                 'Actions': {
                        'E': {
                            'Action': self.email,
                            'arguments': 'graph',
                            'Label': "Email graph"
                            },
                        'S': {
                            'Action': self.showHouseholds,
                            'Label': "Select"
                            },
                        '<': {
                            'Action': self.prevHH,
                            'Label': "Prev"
                            },
                        '>': {
                            'Action': self.nextHH,
                            'Label': "Next"
                            },
                    }
                 }
            }
        return Screen

    def setMainMenu(self):
        # Show main text
        mainScreenText = self.getMenuText()
        self.value.set_values(mainScreenText)
        self.wMain.values = mainScreenText
        self.wMain.display()

        # Show top status bar
        self.myStatus = Screen[ScreenKey]['Name']
        self.wStatus1.value = "METER - %s - (%s)" % (self.myStatus, getHost())
        self.wStatus1.display()

        # Show permanent commands in bottom status line
        commandStr = ''
        for ActionKey in sorted(MasterKeysLabels):
            commandStr = ("%s   [%s]%s" % (commandStr,ActionKey, MasterKeysLabels[ActionKey]))
        self.wStatus2.value = "Commands:  %s" % commandStr
        self.wStatus2.display()


    
    def show_Tables(self, *args, **keywords):
        self.myStatus = 'Tables'
        self.display_tables()

    def list_household(self):
        MeterApp._Forms['MAIN'].display_selected_data("Household")

    def list_meta(self):
        MeterApp._Forms['MAIN'].display_selected_data("Meta")

    def list_contacts(self):
        MeterApp._Forms['MAIN'].display_selected_data("Contact")


    def show_EditContact(self, *args, **keywords):
        self.parentApp.switchForm('EditContact')

    def show_EditHousehold(self, *args, **keywords):
        self.parentApp.switchForm('EditHousehold')


    def IgnoreForNow(self):
        pass

    def toggleDatabase(self):
        toggleDatabase()
        MeterApp._Forms['MAIN'].setMainMenu()

    def add_contact(self):
        if self.editing:
            self.parentApp.switchForm('NewContact')

    def afterEditing(self):
        if self.editing:
            self.parentApp.switchForm('NewContact')

    def display_selected_data(self, displayModus):
        # pull SQL data and display                     #display_data
        self.myStatus = displayModus
        self.wStatus1.value = "METER " + self.myStatus + " selection"
        if (displayModus == "Contact"):
            sqlq = "SELECT * FROM Contact"
            result = getSQL(sqlq)

        elif (displayModus == "Households"):
            result = [
                       "{:<8}".format('HH ID') +\
                       "{:<7}".format('Status') +\
                       "{:<20}".format('Name') +\
                       "{:<13}".format('Date') +\
                       "{:<3}".format('#') +\
                       "{:<25}".format('Comment') ]

            global ScreenKey
            fields ='idHousehold, timestamp, Contact_idContact, date_choice, CONVERT(comment USING utf8), status' 
            sqlq = "SELECT " + fields + " FROM Household WHERE " + Screen[ScreenKey]['Criterium'] +";"
            # executeSQL(sqlq)
            hh_result = getSQL(sqlq)
            for hh in hh_result:
                thisHHid      = str(hh['idHousehold'])
                thisTimeStamp = getDateTimeFormated(str(hh['timestamp']))
                thisContact   = str(hh['Contact_idContact'])
                thisDate      = getDateChoice(thisHHid)
                thisComment   = str(hh['CONVERT(comment USING utf8)'])
                thisStatus    = str(hh['status'])
                result = result + [\
                        "{:<7}".format(thisHHid) + '\t'\
                        "{:<7}".format(thisStatus) +\
                        "{:<20}".format(getNameOfContact(thisContact)) +\
                        "{:<13}".format(thisDate) +\
                        "{:<3}".format(str(getParticipantCount(thisHHid))) +\
                        "{:<25}".format(thisComment) ]


        elif (displayModus == "Household"):
            sqlq = "SELECT idHousehold FROM Household WHERE Contact_idContact = '" + contactID + "'"
            result = getSQL(sqlq)

        else:
            sqlq = "SELECT * FROM " + self.myStatus
            result = getSQL(sqlq)

        # result is populated, now display result
        displayList = []
        if (displayModus == "Contact"):
            for items in result:

                keys = items.keys()
                values = [items[key] for key in keys]
                displayList.append(self.formated_any(values))
        elif (displayModus == "DataType"):
            for items in result:
                displayList.append(self.formated_two(items))
        else:
            for items in result:
                # displayList.append(self.formated_any(items))
                displayList.append(items)
        # update display
        self.value.set_values(displayList)
        self.wMain.values = self.value.get()  # XXX testj
        self.wMain.display()
        self.wStatus1.display()

        commit()
        # global dbConnection
        # dbConnection.commit()
        # self.wStatus2.display()


    def formated_any(self, tupelItems):
        returnString = ""
        for item in tupelItems:
            returnString += "%s \t\t" % (item)
        return returnString

    def formated_two(self, vl):
        return "%s, %s" % (vl[0], vl[1])

    def display_tables(self):
        self.myStatus = 'Tables'
        self.wStatus1.value = "METER " + self.myStatus
        sqlq = "SHOW TABLES"
        results = getSQL(sqlq)
        displayList = []
        for items in results:
            displayList.append(items['Tables_in_Meter'])

        # self.wMain.values = displayList
        self.value.set_values(displayList)
        self.wMain.values = self.value.get()  # XXX testj
        self.wMain.display()
        # self.wMain.values = self.formated_word(result)
        # return result

    def exit_application(self, command_line=None, widget_proxy=None, live=None):
        global cursor
        cursor.close()
        self.parentApp.setNextForm(None)
        self.editing = False
        self.parentApp.switchFormNow()

class editContactForm(nps.Form):
    # gets fields from database, collects new entries

    def beforeEditing(self):
        sqlq = "SHOW columns from Contact;"
        tabledata = getSQL(sqlq)
        self.contactID = getContact(householdID)
        sqlq = "SELECT * from Contact WHERE idContact = %s;" % self.contactID
        result = getSQL(sqlq)[0]
        self.contactData = []
        for field in tabledata:
            self.contactData.append(self.add(nps.TitleText, 
                     name=field['Field'],
                     value="%s"%result[field['Field']]))

    def afterEditing(self):
        for i in range(len(self.contactData)):
            sqlq="UPDATE Contact SET `%s` = '%s' WHERE idContact = '%s'" %\
                    ( self.contactData[i].name,
                      self.contactData[i].value,
                      self.contactID )
            executeSQL(sqlq)
        commit()
        self.parentApp.setNextFormPrevious()

class editHouseholdForm(nps.Form):
    # EditHousehold - Shows all entries for editing

    def beforeEditing(self):
        sqlq = "SHOW columns from Household;"
        tabledata = getSQL(sqlq)
        sqlq = "SELECT * from Household WHERE idHousehold = %s;" % householdID
        result = getSQL(sqlq)[0]
        self.contactData = []
        for field in tabledata:
            self.contactData.append(self.add(nps.TitleText, 
                     name=field['Field'],
                     value="%s"%result[field['Field']]))

    def afterEditing(self):
        for i in range(len(self.contactData)):
            sqlq="UPDATE Household SET `%s` = '%s' WHERE idHousehold = '%s'" %\
                    ( self.contactData[i].name,
                      self.contactData[i].value,
                      householdID )
            executeSQL(sqlq)
        commit()
        self.parentApp.setNextFormPrevious()

class newContactForm(nps.Form):
    # gets fields from database, collects new entries
    def create(self):
        # get Household fields
        self.ColumnName = []
        self.ColumnEntry = []

    def beforeEditing(self):
        sqlq = "SHOW columns from Contact;"
        tabledata = getSQL(sqlq)
        for field in tabledata:
            self.ColumnName.append(field['Field'])
        self.ColumnName.pop()       # remove 'recorded' field (auto completed)
        
        for item in range(0, len(self.ColumnName)):
            self.ColumnEntry.append(self.add(nps.TitleText,
                                    name=self.ColumnName[item]))
        # self.ColumnName.pop(0)   # to leave out the ID column
        # cursor.close()

    def afterEditing(self):
        global contactID
        global householdID

        # combine all column names into comma separated string with ``
        sqlColumnString = "`"+self.ColumnName[0]+"`"
        for item in self.ColumnName[1:]:
            sqlColumnString = sqlColumnString + (",`"+item+"`")

        sqlEntryString = "'"+self.ColumnEntry[0].value+"'"
        for item in self.ColumnEntry[1:]:
            sqlEntryString = sqlEntryString + (",'"+item.value+"'")

        # create contact
        sqlq = "INSERT INTO `Contact`(" + sqlColumnString + ") \
            VALUES ("+sqlEntryString+")"
        contactID = executeSQL(sqlq)
        commit()
        
        # create household
        sqlq = "INSERT INTO `Household`(Contact_idContact, security_code) \
            VALUES (%s, 123);" % contactID
        householdID = executeSQL(sqlq)
        commit()
        self.parentApp.setNextFormPrevious()


class metaFileInformation(nps.Form):
    # The MetaForm
    # display all .meta files in /METER/
    def init(self):
        self.fileList = []
        self.reject_fileList = []
        self.selectIndex = []
        self.selectCounter = 0
        self.metaIDs = []
        self.collectionDate = []
        self.dataType = []
        self.duration = []
        self.displayString = []
        self.reject_Index = []
        self.reject_Counter = 0
        self.reject_contactID = []
        self.reject_collectionDate = []
        self.reject_dataType = []
        self.reject_duration = []
        self.reject_displayString = []

    def create(self):
        self.init()
        self.FileSelection = self.add(nps.TitleMultiSelect, max_height=9,
                                      name="Which files should be uploaded?",
                                      scroll_exit=True)
        self.FileRejection = self.add(nps.TitleMultiSelect, max_height=15,
                                      name="These files will be deleted (uncheck to save them)?",
                                      scroll_exit=True)

    def beforeEditing(self):
        self.FileSelection.value = []
        self.init()

        # set up file names
        global filePath

        # 7 Nov 2016 XXX allCSVfiles = filePath + '*.csv'


        # BUG: empty list causes a "-1" entry to show next time...
        # XXX 27 Jan 2017 ACTION
        # remove all "id / config and debug files"
        # if list is empty jump right out ... 

        allCSVfiles = filePath + 'METER/*.csv'
        allJSONfiles = filePath + 'METER/*.json'
        CSVfileList = glob.glob(allCSVfiles)
        CSVfileList = CSVfileList + glob.glob(allJSONfiles)

        for DataFile in CSVfileList:
            recordsInFile = sum(1 for line in open(DataFile))
            thisFileName = DataFile.split('.csv')[0]
            thisFileName = thisFileName.split('.json')[0]

            if (recordsInFile < 1):
                call('mv ' + thisFileName + '.meta ~/.Trash/', shell=True)
                call('mv ' + thisFileName + '.csv ~/.Trash/', shell=True)
            elif (recordsInFile > 80000):
                global householdID
                # only full 24 hour recordings are of interest
                # (that would be 86400 seconds)

                # the split() takes the Watt column after first ',' before '\n'
                meanPower =  sum(float(line.split(',')[1].split('\n')[0]) for line in open(DataFile)) / recordsInFile

                thisMeta = getMetaData(thisFileName + '.meta', "Meta ID")
                householdID = getHouseholdForMeta(thisMeta) 
                thisDateChoice = getDateChoice(householdID)
                self.selectIndex.append(self.selectCounter)
                self.fileList.append(thisFileName)
                self.metaIDs.append(thisMeta)

                self.collectionDate.append(getMetaData(thisFileName + '.meta', "Date"))
                self.dataType.append(getMetaData(thisFileName+'.meta', "Data type"))
                thisDuration = ("%.1f" % (recordsInFile / 3600.0))

                self.displayString.append(str(self.selectCounter) + '. ID: ' +
                                     thisMeta + ' ' + self.dataType[-1] +
                                     ' on ' + self.collectionDate[-1] + ' (' +thisDateChoice+ ') for ' +
                                     thisDuration + ' h ('+ ("%.1f" % meanPower) +'W)')
                self.selectCounter += 1

            elif ('act' in DataFile):
                self.selectIndex.append(self.selectCounter)
                self.fileList.append(thisFileName)
                self.metaIDs.append(os.path.basename(DataFile).split('_')[0])        # filename is metaID+'_act.csv'
                self.collectionDate.append(getDateOfFirstEntry(DataFile,1))           # take date from first entry in column 1 (2nd col)
                self.dataType.append("A")
                self.duration.append(recordsInFile)
                self.displayString.append(str(self.selectCounter) + '. ID: ' +
                                     self.metaIDs[-1] + ' ' + self.dataType[-1] +
                                     ' with ' +
                                     str(self.duration[-1]) + ' records')
                self.selectCounter += 1

            elif ('ind' in DataFile):
                self.selectIndex.append(self.selectCounter)
                self.fileList.append(thisFileName)
                self.metaIDs.append(os.path.basename(DataFile).split('_')[0])        # filename is metaID+'_ind.csv'

                self.collectionDate.append(getDateOfFirstEntry(DataFile,0))           # take date from first entry in column 0 (1nd col)
                self.dataType.append("I")
                self.duration.append(recordsInFile)
                self.displayString.append(str(self.selectCounter) + '. ID: ' +
                                     self.metaIDs[-1] + ' ' + self.dataType[-1] +
                                     ' with ' + str(self.duration[-1]) + ' records')
                self.selectCounter += 1
            elif ('config' in DataFile):
                pass
            else:
                self.reject_Index.append(self.reject_Counter)
                self.reject_fileList.append(thisFileName)
                self.reject_contactID.append(getMetaData(thisFileName +
                                        '.meta', "Contact ID"))
                self.reject_collectionDate.append(getMetaData(thisFileName +
                                             '.meta', "Date"))
                self.reject_dataType.append(getMetaData(thisFileName +
                                       '.meta', "Data type"))
                self.reject_duration.append(round(recordsInFile / 3600.0, 2))
                self.reject_displayString.append(str(self.reject_Counter) + '.\t ID: ' +
                                            self.reject_contactID[-1] + ' ' +
                                            self.reject_dataType[-1] + ' on ' +
                                            self.reject_collectionDate[-1] +
                                            ' for ' + str(self.reject_duration[-1]) +
                                            ' hours')
                self.reject_Counter += 1
        self.FileSelection.values = self.displayString
        self.FileSelection.value = self.selectIndex
        self.FileRejection.values = self.reject_displayString


    def afterEditing(self):
        for i in self.FileSelection.value:
            uploadDataFile(self.fileList[i],self.dataType[i],self.metaIDs[i],self.collectionDate[i])   # insert to database

        for FileIndex in self.FileRejection.value:                                      # delete all other files
            call('mv ' + self.reject_fileList[FileIndex] +
                 '.meta ~/.Trash/', shell=True)
            call('mv ' + self.reject_fileList[FileIndex] +
                 '.csv ~/.Trash/', shell=True)

        # tidy up any left over files
        call('mv ' + filePath + '/METER/*.csv ' + archivePath, shell=True)
        call('mv ' + filePath + '/METER/*.meta ' + archivePath, shell=True)
        call('mv ' + filePath + '/METER/*_act.json ' + archivePath, shell=True)

        # switch to "Processed" and display the most recent addition
        global ScreenKey
        # ScreenKey = modi[2] # display as "Processed"
        ScreenKey = "7" # display as "Processed"
        self.parentApp.setNextFormPrevious()


class MeterTheme(nps.ThemeManager):
    default_colors = {
    'DEFAULT'     : 'WHITE_BLACK',
    'FORMDEFAULT' : 'GREEN_BLACK',
    'NO_EDIT'     : 'BLUE_BLACK',
    'STANDOUT'    : 'CYAN_BLACK',
    'CURSOR'      : 'GREEN_BLACK',
    'CURSOR_INVERSE': 'BLACK_WHITE',
    'LABEL'       : 'GREEN_BLACK',
    'LABELBOLD'   : 'WHITE_BLACK',
    'CONTROL'     : 'YELLOW_BLACK',
    'IMPORTANT'   : 'GREEN_BLACK',
    'SAFE'        : 'GREEN_BLACK',
    'WARNING'     : 'YELLOW_BLACK',
    'DANGER'      : 'RED_BLACK',
    'CRITICAL'    : 'BLACK_RED',
    'GOOD'        : 'GREEN_BLACK',
    'GOODHL'      : 'GREEN_BLACK',
    'VERYGOOD'    : 'BLACK_GREEN',
    'CAUTION'     : 'YELLOW_BLACK',
    'CAUTIONHL'   : 'BLACK_YELLOW',
    }

class MeterForms(nps.NPSAppManaged):
    def onStart(self):
        #nps.setTheme(nps.Themes.ColorfulTheme)
        nps.setTheme(MeterTheme)
        self.addForm('MAIN', MeterMain, lines=36)
        self.addForm('NewContact', newContactForm, name='New Contact')
        self.addForm('EditContact', editContactForm, name='Edit Contact')
        self.addForm('EditHousehold', editHouseholdForm, name='Edit Household')
        self.addForm('MetaForm', metaFileInformation, name='Meta Data')

if __name__ == "__main__":
    MeterApp = MeterForms()
    MeterApp.run()
    exit()
