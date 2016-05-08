"""
WinEDS Converter tool
"""

from setuptools import setup, find_packages

setup(
    name='WinEDS-Converter',
    version='0.6',
    license='BSD-3-Clause',
    description="WinEDS Converter tool",
    url="https://github.com/cjerdonek/wineds-converter",
    author="Chris Jerdonek",
    author_email="chris.jerdonek@gmail.com",
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
    ],
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'wineds-convert=pywineds.run:main',
        ],
    },
)
