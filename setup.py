"""
WinEDS Converter tool

For more information, see:
https://github.com/cjerdonek/wineds-converter
"""

from setuptools import setup, find_packages

setup(
    name='WinEDS-Converter',
    version='0.6',
    description=__doc__,
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'wineds-convert=pywineds.run:main',
        ],
    },
)
