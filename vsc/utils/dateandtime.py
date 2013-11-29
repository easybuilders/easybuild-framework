##
#
# Copyright 2012-2013 Ghent University
#
# This file is part of vsc-base,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/vsc-base
#
# vsc-base is free software: you can redistribute it and/or modify
# it under the terms of the GNU Library General Public License as
# published by the Free Software Foundation, either version 2 of
# the License, or (at your option) any later version.
#
# vsc-base is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public License
# along with vsc-base. If not, see <http://www.gnu.org/licenses/>.
##
"""
Module with various convenience functions and classes to deal with date, time and timezone

@author: Stijn De Weirdt (Ghent University)
"""

import calendar
import re
import time as _time
from datetime import tzinfo, timedelta, datetime, date

try:
    any([0, 1])
except:
    from vsc.utils.missing import any


class FancyMonth:
    """Convenience class for month math"""
    def __init__(self, tmpdate=None, year=None, month=None, day=None):
        """Initialise the month based on first day of month of tmpdate"""

        if tmpdate is None:
            tmpdate = date.today()

        if day is None:
            day = tmpdate.day
        if month is None:
            month = tmpdate.month
        if year is None:
            year = tmpdate.year

        self.date = date(year, month, day)

        self.first = None
        self.last = None
        self.nrdays = None

        # when calculating deltas, include non-full months
        #   eg when True, nr of months between last day of month
        #   and first day of following month is 2
        self.include = True

        self.set_details()

    def set_details(self):
        """Get first/last day of the month of date"""
        class MyCalendar(object):
            """Backport minimal calendar.Calendar code from 2.7 to support itermonthdays in 2.4"""
            def __init__(self, firstweekday=0):
                self.firstweekday = firstweekday  # 0 = Monday, 6 = Sunday

            def itermonthdates(self, year, month):
                """
                Return an iterator for one month. The iterator will yield datetime.date
                values and will always iterate through complete weeks, so it will yield
                dates outside the specified month.
                """
                _date = date(year, month, 1)
                # Go back to the beginning of the week
                days = (_date.weekday() - self.firstweekday) % 7
                _date -= timedelta(days=days)
                oneday = timedelta(days=1)
                while True:
                    yield _date
                    _date += oneday
                    if _date.month != month and _date.weekday() == self.firstweekday:
                        break

            def itermonthdays(self, year, month):
                """
                Like itermonthdates(), but will yield day numbers. For days outside
                the specified month the day number is 0.
                """
                for _date in self.itermonthdates(year, month):
                    if _date.month != month:
                        yield 0
                    else:
                        yield _date.day

        if 'Calendar' in dir(calendar):  # py2.5+
            c = calendar.Calendar()
        else:
            c = MyCalendar()
        self.nrdays = len([x for x in c.itermonthdays(self.date.year, self.date.month) if x > 0])

        self.first = date(self.date.year, self.date.month, 1)

        self.last = date(self.date.year, self.date.month, self.nrdays)

    def get_start_end(self, otherdate):
        """Return tuple date and otherdate ordered oldest first"""
        if self.date > otherdate:
            start = otherdate
            end = self.date
        else:
            start = self.date
            end = otherdate

        return start, end

    def number(self, otherdate):
        """Calculate the number of months between this month (date actually) and otherdate
        """
        if self.include is False:
            msg = "number: include=False not implemented"
            raise(Exception(msg))
        else:
            startdate, enddate = self.get_start_end(otherdate)

            if startdate == enddate:
                nr = 0
            else:
                nr = (enddate.year - startdate.year) * 12 + enddate.month - startdate.month + 1

        return nr

    def get_other(self, shift=-1):
        """Return month that is shifted shift months: negative integer is in past, positive is in future"""
        new = self.date.year * 12 + self.date.month - 1 + shift
        return self.__class__(date(new // 12, new % 12 + 1, 01))

    def interval(self, otherdate):
        """Return time ordered list of months between date and otherdate"""
        if self.include is False:
            msg = "interval: include=False not implemented"
            raise(Exception(msg))
        else:
            nr = self.number(otherdate)
            startdate, enddate = self.get_start_end(otherdate)

            start = self.__class__(startdate)
            all_dates = [start.get_other(m) for m in range(nr)]

        return all_dates

    def parser(self, txt):
        """Based on strings, return date: eg BEGINTHIS returns first day of the current month"""
        supportedtime = ('BEGIN', 'END',)
        supportedshift = ['THIS', 'LAST', 'NEXT']
        regtxt = r"^(%s)(%s)?" % ('|'.join(supportedtime), '|'.join(supportedshift))

        reseervedregexp = re.compile(regtxt)
        reg = reseervedregexp.search(txt)
        if not reg:
            msg = "parse: no match for regexp %s for txt %s" % (regtxt, txt)
            raise(Exception(msg))

        shifttxt = reg.group(2)
        if shifttxt is None or shifttxt == 'THIS':
            shift = 0
        elif shifttxt == 'LAST':
            shift = -1
        elif shifttxt == 'NEXT':
            shift = 1
        else:
            msg = "parse: unknown shift %s (supported: %s)" % (shifttxt, supportedshift)
            raise(Exception(msg))

        nm = self.get_other(shift)

        timetxt = reg.group(1)
        if timetxt == 'BEGIN':
            res = nm.first
        elif timetxt == 'END':
            res = nm.last
        else:
            msg = "parse: unknown time %s (supported: %s)" % (timetxt, supportedtime)
            raise(Exception(msg))

        return res


def date_parser(txt):
    """Parse txt

    @type txt: string

    @param txt: date to be parsed. Usually in C{YYYY-MM-DD} format,
    but also C{(BEGIN|END)(THIS|LAST|NEXT)MONTH}, or even
    C{(BEGIN | END)(JANUARY | FEBRUARY | MARCH | APRIL | MAY | JUNE | JULY | AUGUST | SEPTEMBER | OCTOBER | NOVEMBER | DECEMBER)}
    """

    reserveddate = ('TODAY',)
    testsupportedmonths = [txt.endswith(calendar.month_name[x].upper()) for x in range(1, 13)]

    if txt.endswith('MONTH'):
        m = FancyMonth()
        res = m.parser(txt)
    elif any(testsupportedmonths):
        # set day=1 or this will fail on day's with an index more then the count of days then the month you want to parse
        # e.g. will fail on 31'st when trying to parse april
        m = FancyMonth(month=testsupportedmonths.index(True) + 1, day=1)
        res = m.parser(txt)
    elif txt in reserveddate:
        if txt in ('TODAY',):
            m = FancyMonth()
            res = m.date
        else:
            msg = 'dateparser: unimplemented reservedword %s' % txt
            raise(Exception(msg))
    else:
        try:
            datetuple = [int(x) for x in txt.split("-")]
            res = date(*datetuple)
        except:
            msg = ("dateparser: failed on '%s' date txt expects a YYYY-MM-DD format or "
                   "reserved words %s") % (txt, ','.join(reserveddate))
            raise(Exception(msg))

    return res


def datetime_parser(txt):
    """Parse txt: tmpdate YYYY-MM-DD HH:MM:SS.mmmmmm in datetime.datetime
        - date part is parsed with date_parser
    """
    tmpts = txt.split(" ")
    tmpdate = date_parser(tmpts[0])

    datetuple = [tmpdate.year, tmpdate.month, tmpdate.day]
    if len(tmpts) > 1:
        # add hour and minutes
        datetuple.extend([int(x) for x in tmpts[1].split(':')[:2]])

        try:
            sects = tmpts[1].split(':')[2].split('.')
        except:
            sects = [0]
        # add seconds
        datetuple.append(int(sects[0]))
        if len(sects) > 1:
            # add microseconds
            datetuple.append(int(float('.%s' % sects[1]) * 10 ** 6))

    res = datetime(*datetuple)

    return res


def timestamp_parser(timestamp):
    """Parse timestamp to datetime"""
    return datetime.fromtimestamp(float(timestamp))

#
# example code from http://docs.python.org/library/datetime.html
# Implements Local, the local timezone
#

ZERO = timedelta(0)
HOUR = timedelta(hours=1)


# A UTC class.
class UTC(tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO

utc = UTC()


class FixedOffset(tzinfo):
    """Fixed offset in minutes east from UTC.

    This is a class for building tzinfo objects for fixed-offset time zones.
    Note that FixedOffset(0, "UTC") is a different way to build a
    UTC tzinfo object.
    """
    def __init__(self, offset, name):
        self.__offset = timedelta(minutes=offset)
        self.__name = name

    def utcoffset(self, dt):
        return self.__offset

    def tzname(self, dt):
        return self.__name

    def dst(self, dt):
        return ZERO


STDOFFSET = timedelta(seconds=-_time.timezone)
if _time.daylight:
    DSTOFFSET = timedelta(seconds=-_time.altzone)
else:
    DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET


class LocalTimezone(tzinfo):
    """
    A class capturing the platform's idea of local time.
    """

    def utcoffset(self, dt):
        if self._isdst(dt):
            return DSTOFFSET
        else:
            return STDOFFSET

    def dst(self, dt):
        if self._isdst(dt):
            return DSTDIFF
        else:
            return ZERO

    def tzname(self, dt):
        return _time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        tt = (dt.year, dt.month, dt.day,
              dt.hour, dt.minute, dt.second,
              dt.weekday(), 0, 0)
        stamp = _time.mktime(tt)
        tt = _time.localtime(stamp)
        return tt.tm_isdst > 0

Local = LocalTimezone()
