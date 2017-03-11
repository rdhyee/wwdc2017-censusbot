# -*- coding: utf-8 -*-
__all__ = ['WikidataWrapper', 'wikidata_states']

# I learned a lot from 
# [census-wikidata-bot/addPopValues.py](https://github.com/CommerceDataService/census-wikidata-bot/blob/3e548e1e0dfe80f2fb950c61fba97be49347b8e8/addPopValues.py)

from itertools import islice
import pandas as pd
from pandas import DataFrame, Series

import requests
import arrow

import pywikibot, json, os, requests
from pywikibot.data import api
from pywikibot import pagegenerators as pg

class WikidataWrapper(object):
    def __init__(self, mode='wikidata', site_label='wikidata'):
        self.mode = mode
        self.site_label = site_label
        self.site = pywikibot.Site(mode, 'wikidata')
        self.repo = self.site.data_repository()
        if self.mode == 'wikidata':
            self.p_population = u'P1082'
            self.p_point_in_time = u'P585'
            self.p_determination_method = u'P459'
        else:
            self.p_population = u'P63'
            self.p_point_in_time = u'P66'
            self.p_determination_method = u'P144'
    def item (self, id_):
        item = pywikibot.ItemPage(self.repo, id_)  # This will be functionally the same as the other item we defined
        item.get()  # you need to call it to access any data.
        return item
    
    def item_label(self, item, lang='en'):
        """
        assuming an item in which get() has been run
        """
        return item.labels.get(lang)    

    def date_claim_extract(self, date_claim):

        # can there be more than one of point in time claims?  I guess yes
        # here assume 1 and only 1 point in time claim
        pop_claim_date = date_claim.target

        # how to interconvert WbTime from datetime?  (doesn't matter)
        # precision defined in 
        # https://github.com/wikimedia/pywikibot-core/blob/51bc9671d1d2f0719dc5258616e87c4ff32c3769/pywikibot/__init__.py#L404-L419

        return (pop_claim_date.year, pop_claim_date.month, pop_claim_date.day,  pop_claim_date.precision )


    def pop_claims(self, item):
        # pull up populate claims
        claims = item.claims.get(self.p_population)
        for claim in claims:
            target = claim.getTarget()
            date_claims = [date_claim_extract(c) for c in claim.qualifiers.get(p_point_in_time)]
            yield (claim, date_claims)

    def date_claims_of_interest(self, item):
        """
        claims in 2010 that aren't April 1, 2010
        """
        # pull up populate claims
        claims = item.claims.get(self.p_population)
        for claim in claims:
            date_claims = claim.qualifiers.get(self.p_point_in_time)
            if date_claims is None:
                date_claims = []
            for date_claim in date_claims:
                pop_claim_date = date_claim.target
                if (pop_claim_date.year == 2010 and 
                    (pop_claim_date.year, pop_claim_date.month, pop_claim_date.day) <> (2010,4,1)):
                    yield {'population_claim':claim, 
                           'date_in_time_claim':date_claim, 
                           'date_for_claim':self.date_claim_extract(date_claim)}
 

    def fix_claims_of_interest(self, ids_for_items, max_n=None):
        
        for item_id in islice(ids_for_items,max_n):
            item = self.item(item_id)
            claims_of_interest = list(self.date_claims_of_interest(item))
            print (self.item_label(item)), claims_of_interest

            for t in claims_of_interest:
                print (t['population_claim'].target, t['date_in_time_claim'])
                # remove wrong qualifier
                t['population_claim'].removeQualifier(t['date_in_time_claim'])
                # replace with proper qualifier
                qualifier = pywikibot.Claim(self.repo, self.p_point_in_time)
                # April 1, 2010 with precision of 1 day
                target = pywikibot.WbTime(2010,4,1, precision=11)
                qualifier.setTarget(target)
                t['population_claim'].addQualifier(qualifier)

# getting list of states


wikdata_url = "https://query.wikidata.org/sparql?"

states_query = """

SELECT ?state ?stateLabel 
WHERE {
  
{?state wdt:P31 wd:Q35657} UNION 
     {?state wdt:P1566 "4138106"} . # we want wd:Q61
  
 SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
  
}

"""

def xsd_coerce(value, datatype=None):
    if datatype is None:
        return value
    if datatype == 'http://www.w3.org/2001/XMLSchema#decimal':
        return float(value)
    if datatype == 'http://www.w3.org/2001/XMLSchema#dateTime':
        return arrow.get(value)
    
    return value

def sparqljson_items(sjson):
    """no attempt to use type infor for now"""
    
    headers = sjson['head']['vars']
    results = sjson['results']['bindings']
    
    return [dict([(k,v['value']) for (k,v) in result.items()]) 
         for result in results]

def sparqljson_to_df(sjson, convert_type=True):
    """simple type conversion"""
    
    results = sjson['results']['bindings']
    
    outputs = []
    for result in results:
        
        output = {}
        for (k,v) in result.items():
            if convert_type:
                output[k] = xsd_coerce(v['value'], v.get('datatype'))
            else:
                output[k] = v['value']
        outputs.append(output)
        
    return DataFrame(outputs)
 
def wikidata_states():

	r = requests.get(wikdata_url, params = {'query':states_query, 'format':'json'})
	states = dict([(item['state'].split('/')[-1], item['stateLabel']) for item in sparqljson_items(r.json())])

	return states