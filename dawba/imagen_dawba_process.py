#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Re-encode and anonymize DAWBA files (BL, FU1, FU2 and FU3).

This script replaces the Scito anoymization pipeline which does not
seem to be working anymore for DAWBA files.

==========
Attributes
==========

Input
-----

DAWBA_BL_MASTER_DIR : str
    Location of BL PSC1-encoded files.
DAWBA_FU1_MASTER_DIR : str
    Location of FU1 PSC1-encoded files.
DAWBA_FU2_MASTER_DIR : str
    Location of FU2 PSC1-encoded files.
DAWBA_FU3_MASTER_DIR : str
    Location of FU3 PSC1-encoded files.

Output
------

DAWBA_BL_PSC2_DIR : str
    Location of BL PSC2-encoded files.
DAWBA_FU1_PSC2_DIR : str
    Location of FU1 PSC2-encoded files.
DAWBA_FU2_PSC2_DIR : str
    Location of FU2 PSC2-encoded files.
DAWBA_FU3_PSC2_DIR : str
    Location of FU3 PSC2-encoded files.

"""

DAWBA_BL_MASTER_DIR = '/neurospin/imagen/BL/RAW/PSC1/dawba'
DAWBA_BL_PSC2_DIR = '/neurospin/imagen/BL/RAW/PSC2/dawba'
DAWBA_FU1_MASTER_DIR = '/neurospin/imagen/FU1/RAW/PSC1/dawba'
DAWBA_FU1_PSC2_DIR = '/neurospin/imagen/FU1/RAW/PSC2/dawba'
DAWBA_FU2_MASTER_DIR = '/neurospin/imagen/FU2/RAW/PSC1/dawba'
DAWBA_FU2_PSC2_DIR = '/neurospin/imagen/FU2/RAW/PSC2/dawba'
DAWBA_FU3_MASTER_DIR = '/neurospin/imagen/FU3/RAW/PSC1/dawba'
DAWBA_FU3_PSC2_DIR = '/neurospin/imagen/FU3/RAW/PSC2/dawba'

MISSING_DAWBA1_CODES = {
    # DAWBA1 codes, missing for some reason - just ignore them...
    '19042',
    '19044',
    '19045',
    '19046',
    '19047',
    '19048',
    '19049',
    '19050',
    '19051',
    '23094',
    '23095',
    '23096',
    '23097',
    '23098',
    '23099',
    '23100',
    '23101',
    '23102',
    '23103',
    '23104',
    '23105',
    '23106',
    '23107',
    '23108',
    '23109',
    '23110',
    '23112',
    '23881',
    '27361',
    '27512',
    '28117',
    '28694',
    '31469',
    '31470',
    '31471',
    '31473',
    '38297',
    '38298',
    '38299',
    '38300',
    '38301',
}
WITHDRAWN_DAWBA_CODES = {
    # see thread "DAWBA3 codes conversion table" from 2015-05-18
    '127657',
    # see thread "DAWBA3 codes conversion table" from 2015-12-15
    '128847',
    '127658',
    '132983',
    '129716',
    '129500',
}

import logging
logging.basicConfig(level=logging.INFO)

import os
from datetime import datetime

# import ../imagen_databank
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
from imagen_databank import PSC2_FROM_PSC1, PSC1_FROM_PSC2
from imagen_databank import PSC2_FROM_DAWBA
from imagen_databank import DOB_FROM_PSC2


def _create_psc2_file(psc2_from_dawba, dawba_path, psc2_path):
    """Anonymize and re-encode a DAWBA questionnaire from DAWBA to PSC2.

    DAWBA questionnaire files are CSV files.

    Columns containing a date will be modified and the date will converted to
    the age of the subject in days, as required by the anonymization process.

    Parameters
    ----------
    psc2_from_dawba: map
        Conversion table, from DAWBA to PSC2.
    dawba_path: str
        Input: DAWBA-encoded CSV file.
    psc2_path: str
        Output: PSC2-encoded CSV file.

    """
    with open(dawba_path, 'r') as dawba_file:
        # identify columns to anonymize in header
        header = dawba_file.readline()
        convert = [i for i, field in enumerate(header.split('\t'))
                   if 'sstartdate' in field or 'p1startdate' in field]
        with open(psc2_path, 'w') as psc2_file:
            psc2_file.write(header)
            for line in dawba_file:
                items = line.split('\t')
                dawba = items[0]
                if dawba in psc2_from_dawba:
                    psc2 = psc2_from_dawba[dawba]
                    logging.info('converting subject {0} from DAWBA to PSC2'
                                 .format(PSC1_FROM_PSC2[psc2]))
                    items[0] = psc2
                    # convert dates to subject age in days
                    for i in convert:
                        if items[i] != '':
                            if psc2 in DOB_FROM_PSC2:
                                startdate = datetime.strptime(items[i],
                                                              '%d.%m.%y').date()
                                birthdate = DOB_FROM_PSC2[psc2]
                                age = startdate - birthdate
                                logging.info('age of subject {0}: {1}'
                                             .format(PSC1_FROM_PSC2[psc2], age.days))
                                items[i] = str(age.days)
                            else:
                                items[i] = ''
                    psc2_file.write('\t'.join(items))
                else:
                    if dawba in WITHDRAWN_DAWBA_CODES:
                        logging.info('withdrawn DAWBA code: {0}'.format(dawba))
                    elif dawba in MISSING_DAWBA1_CODES:
                        logging.warning('missing DAWBA1 codes: {0}'.format(dawba))
                    else:
                        logging.error('DAWBA code missing from conversion table: {0}'.format(dawba))
                    continue


def create_psc2_files(psc2_from_dawba, master_dir, psc2_dir):
    """Anonymize and re-encode all DAWBA questionnaires within a directory.

    DAWBA-encoded files are read from `master_dir`, anoymized and converted
    from DAWBA codes to PSC2, and the result is written in `psc2_dir`.

    Parameters
    ----------
    psc2_from_dawba: map
        Conversion table, from DAWBA to PSC2.
    master_dir: str
        Input directory with DAWBA-encoded questionnaires.
    psc2_dir: str
        Output directory with PSC2-encoded and anonymized questionnaires.

    """
    for master_file in os.listdir(master_dir):
        master_path = os.path.join(master_dir, master_file)
        psc2_path = os.path.join(psc2_dir, master_file)
        _create_psc2_file(psc2_from_dawba, master_path, psc2_path)


def main():
    create_psc2_files(PSC2_FROM_DAWBA,
                      DAWBA_BL_MASTER_DIR, DAWBA_BL_PSC2_DIR)
    create_psc2_files(PSC2_FROM_DAWBA,
                      DAWBA_FU1_MASTER_DIR, DAWBA_FU1_PSC2_DIR)
    create_psc2_files(PSC2_FROM_DAWBA,
                      DAWBA_FU2_MASTER_DIR, DAWBA_FU2_PSC2_DIR)
    create_psc2_files(PSC2_FROM_DAWBA,
                      DAWBA_FU3_MASTER_DIR, DAWBA_FU3_PSC2_DIR)


if __name__ == "__main__":
    main()