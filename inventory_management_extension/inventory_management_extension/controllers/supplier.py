
import frappe 
from frappe import _

def before_save(doc, method=None):
    for cert in doc.custom_certifications:
        abbreviation = abbr(cert.certification)
        cert.abbr = abbreviation
        print(abbreviation)
    
def abbr(text):
    return ''.join(word[0].upper() for word in text.split() if word)