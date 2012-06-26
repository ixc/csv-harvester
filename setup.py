#!/usr/bin/env python
# -*- coding: utf-8 -*-

from distutils.core import setup

setup(
    name='CSV Harvester',
    version='0.1',
    description='A harvesting framework for CSV files.',
    author='The Interaction Consortium',
    author_email='admins@interaction.net.au',
    #url='http://',
    packages=['csv_harvester',],
    license='BSD',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Utilities'
    ],
)
