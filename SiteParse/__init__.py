# -*- coding: utf-8 -*-

import os
import time
import datetime

import hashlib

import httplib2
from lxml import html

import sqlite3
import pickle

import sys
import traceback
from pprint import pprint

######################################################################


class SiteParseError(Exception):
    def __init__(self, message=''):
        self.message = message

    def _get_message(self):
        return self._message

    def _set_message(self, message):
        self._message = message

    message = property(_get_message, _set_message)


######################################################################
######################################################################
# Parser classes

class Parser:
    """ Abstract class for site parsers
    """

    params = {}
    items_xpath = ''
    items = {}

    def __init__(self, params):
        self.params = params

    def make_url(self, params, extparams):
        """ Makes url for the request. Site-specific function """
        raise NotImplementedError()

    ############################################################

    def print_item(self, i):
        """ Print line with item info """
        raise NotImplementedError()

    def print_items(self, items):
        """ Print group of items """
        for i in items:
            self.print_item(i)

    ############################################################

    def parse_item(self, i):
        """ Parse items html blocks to property dicts """
        raise NotImplementedError()

    def hash_item(self, i):
        """ Calculate hash uniquely identifying item """
        raise NotImplementedError()

    def check_item(self, item):
        """ Winnows items according to some parameters """
        # price
        minprice, maxprice = self.params['price']
        if item['price'] < minprice:
            return False
        if maxprice > 0 and item['price'] > maxprice:
            return False

        return True

    def get_items_after_request_hook(self, parsed_body):
        """ Checks the entire request: was it relevant or not """
        pass

    def get_items(self, url):
        """ Get items html blocks, parse them and return.
        There is NO checking for new items, only fetching and parsing
        """
        req = httplib2.Http()
        try:
            headers, body = req.request(url, method='GET')
        except httplib2.ServerNotFoundError:
            return {}

        if headers['status'] != '200':
            raise SiteParseError("site_returned_%s" % headers['status'])

        # parsing returned page
        parsed_body = html.fromstring(body)
        self.get_items_after_request_hook(parsed_body)

        raw_items = parsed_body.xpath(self.items_xpath)

        items = {}
        for i in raw_items:
            try:
                item = self.parse_item(i)
                if self.check_item(item):
                    # saving item
                    h = self.hash_item(item)
                    items[h] = item
            except Exception:
                # exception info
                # etype, e, tb = sys.exc_info()
                traceback.print_exc()
                # print("PARSE ERROR: %s: %s" % (e.errno, e.strerror))
                # traceback.print_tb(tb)
                # item info (and link to the item on the site)
                pprint(i.values())
                for lnk in i.iterlinks():
                    print(lnk)
                # skip this item and proceed
                pass

        return items

    def refresh(self):
        """ Get items, add ones that do not already present in storage
        Check for new items is THERE
        """
        # initialize new items hashes list
        newhashes = []

        # for every query...
        for query in self.params['queries']:
            # ...searching for every category listed...
            for cat in self.params['categories']:
                # ... and crawling through pages before stop getting new items
                for p in range(1, self.params['maxpages']+1):
                    extparams = {'query': query, 'category': cat, 'page': p}
                    _newhashes = self._refresh(extparams)

                    # if no new items found on this page
                    # then we reached the extent where we already searched,
                    # no need to go farther through pages
                    if len(_newhashes) == 0:
                        break

                    # keep all new items found
                    for h in _newhashes:
                        newhashes.append(h)

                    time.sleep(1)

        # return new items hashes list
        return newhashes

    def _refresh(self, extparams):
        """ Service routine that refreshes items
        in the local search area bounded by extparams
        """
        # prepare url
        url = self.make_url(self.params, extparams)

        # get items from the site
        try:
            items = self.get_items(url)
        except SiteParseError as e:
            print("Attention: %s\t(%s, %s, page %s)"
                  % (e.message, ' '.join(extparams['query']),
                     extparams['category'], extparams['page']))
            return []

        # check which items are new
        newhashes = []
        for h, item in items.items():
            if h in self.items:
                # skip already known items
                continue

            ####################
            # Found new item:

            # 1. save it
            self.items[h] = item
            newhashes.append(h)

            # 2. download photos
            dir = "./photo/%s/" % (h)
            if not os.path.isdir(dir):
                os.mkdir(dir)
            for url in item['photourls']:
                fname = url.split('/')[-1]
                if not os.path.exists(dir + fname):
                    self.download_photo("http:" + url, dir + fname)

        return newhashes

    ############################################################

    def init_db(self, path):
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS Items (hash, url, data)")
        cur.close()
        return conn

    def save(self, path, hashes=None):
        """ Save data to database
        Returns number of added new records
        """
        conn = self.init_db(path)
        cur = conn.cursor()

        if hashes is None:
            items = self.items
        else:
            items = {k: self.items[k] for k in hashes}

        newhashes = []
        for k, i in items.items():
            cur.execute("SELECT * FROM Items WHERE hash=?", [k])
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO Items (hash, url, data) VALUES (?, ?, ?)",
                    [k, i['url'], pickle.dumps(i)]
                    )
                newhashes.append(k)

        if len(newhashes) > 0:
            conn.commit()
        cur.close()
        conn.close()
        return newhashes

    def load(self, path):
        """ Load record from db file.
        Resets items dict!
        """
        conn = self.init_db(path)
        cur = conn.cursor()
        cur.execute("SELECT hash, data FROM Items")
        self.items = {k: pickle.loads(i) for k, i in cur}
        cur.close()
        conn.close()

    ############################################################

    def download_photo(self, url, path, req=None):
        """ Downloads an image from a given url
        and saves to the given path
        """
        if req is None:
            # if no request object given, creating it
            req = httplib2.Http()

        headers, data = req.request(url, method='GET')
        with open(path, 'wb') as fh:
            fh.write(data)
        return True


######################################################################
######################################################################

class AvitoParser(Parser):
    """ Class for parsing avito.ru.
    Version 2014-12-01
    """
    items_xpath = ".//*[starts-with(@class, 'item')]"

    def make_url(self, params, extparams):
        return "http://%s/%s/%s?q=%s&p=%i" % \
            (
                params['baseurl'],
                params['location'],

                extparams['category'],
                '+'.join(extparams['query']),
                extparams['page']
            )

    ############################################################

    def print_item(self, i):
        print("""\033[1;31m%s\033[0m
\t%s\t%s\t%s
\thttp://%s\n"""
              % (i['title'],
                 i['price'], i['date'], i['location'],
                 self.params['baseurl']+i['url']))

    ############################################################

    def get_items_after_request_hook(self, parsed_body):
        # checking if query was corrected
        # if so, abandoning this query
        query_correction = parsed_body.xpath(
            ".//*[@class='catalog-correction']")
        if len(query_correction) > 0:
            raise SiteParseError("query_correction")

    def parse_item(self, i):
        """ Parse items html blocks to property dicts
        """
        d = i.xpath("*[@class='description']")[0]

        price = normalize_str(d.xpath("*[@class='about']/text()")[0])
        price = ''.join([x for x in price if str(x).isdigit()])
        if len(price) == 0:
            # price not specified
            price = 0
        else:
            # converting to int
            price = int(price)

        title = normalize_str(d.xpath("*[@class='title']/a/text()")[0])
        url = d.xpath("*[@class='title']/a/@href")[0]

        category_and_company = d.xpath("*[@class='data']/p[1]/text()")
        category = normalize_str(category_and_company[0])
        company = normalize_str(category_and_company[1]) \
            if len(category_and_company) > 1 else ''

        # location
        try:
            location = normalize_str(
                d.xpath("*[@class='data']/p[2]/text()")[0])
        except:
            # for items without location
            location = ''

        date = normalize_str(normalize_date(d.xpath(
            "*[@class='data']/*[@class='date']/text()"
        )[0]))

        # icon URL
        photourls = []
        try:
            photourls.append(i.xpath("*[@class='b-photo']/a/img/@src")[0])
        except:
            # for items without photo
            pass

        return {'price': price,
                'title': title,
                'url': url,

                'category': category,
                'company': company,

                'location': location,
                'date': date,

                'photourls': photourls,
                }

    fields_order = ['price', 'title', 'url', 'category', 'company',
                    'location', 'date', 'photourls']

    def hash_item(self, i):
        """ Calculate hash uniquely identifying item """
        h = hashlib.md5()
        for f in self.fields_order:
            # strings need to be encoded
            h.update(str(i[f]).encode('UTF-8'))
        return h.hexdigest()


######################################################################
######################################################################
# Some helpers


def normalize_date(d):
    """ Convert date from textual form to timestamp
    """
    today = datetime.date.today()
    oneday = datetime.timedelta(1)
    yesterday = today - oneday

    subst = {
        u'Вчера': yesterday.strftime("%d %m"),
        u'Сегодня': today.strftime("%d %m"),
        u'окт.': '10',
        u'нояб.': '11',
    }

    for k, v in subst.items():
        d = d.replace(k, v)

    return d


def normalize_str(s):
    """ Remove all redundant spaces or newlines or tabs
    """
    return ' '.join(s.split()).lower()
