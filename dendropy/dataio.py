#! /usr/bin/env python

############################################################################
##  dataio.py
##
##  Part of the DendroPy library for phylogenetic computing.
##
##  Copyright 2008 Jeet Sukumaran and Mark T. Holder.
##
##  This program is free software; you can redistribute it and/or modify
##  it under the terms of the GNU General Public License as published by
##  the Free Software Foundation; either version 3 of the License, or
##  (at your option) any later version.
##
##  This program is distributed in the hope that it will be useful,
##  but WITHOUT ANY WARRANTY; without even the implied warranty of
##  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##  GNU General Public License for more details.
##
##  You should have received a copy of the GNU General Public License along
##  with this program. If not, see <http://www.gnu.org/licenses/>.
##
############################################################################

"""
Convenience packaging around readers/writers.
"""

import sys
import StringIO

from dendropy.datasets import Dataset
from dendropy.trees import TreesBlock
from dendropy import nexus
from dendropy import nexml
from dendropy import fasta
from dendropy import phylip

############################################################################
## File Formats

NEXUS='NEXUS'
NEWICK='NEWICK'
NEXML='NEXML'
FASTA='FASTA'
PHYLIP='PHYLIP'
FORMATS = [NEXUS, NEXML, NEWICK, FASTA, PHYLIP]

READERS = {
    NEXUS: nexus.NexusReader,
    NEWICK: nexus.NewickReader,
    NEXML: nexml.NexmlReader,
}

WRITERS = {
    NEXUS: nexus.NexusWriter,
    NEWICK: nexus.NewickWriter,
    NEXML: nexml.NexmlWriter,
    FASTA: fasta.FastaWriter,
    PHYLIP: phylip.PhylipWriter,
}

############################################################################
## Wrappers (Reading/Parsing)
   
def dataset_from_file(file, format):
    """
    Returns a Dataset object parsed from the source, where:
        `file`   - can either be a file descriptor object/handle opened 
                   for reading or a string indicating a filepath that 
                   can be opened for reading using open().     
        `format` - file format specification               
    """
    reader = get_reader(format)
    return reader.read_dataset(source_file_handle(file=file))
    
def dataset_from_string(string, format):
    """
    Returns a Dataset object parsed from the source, where:
        `string` - a string containing the data to be parsed.   
        `format` - file format specification               
    """
    reader = get_reader(format)
    return reader.read_dataset(source_file_handle(string=string))    
    
def trees_from_file(file, format):
    """
    Returns a *list* of TreesBlock objects parsed from the source, where:
        `file`   - can either be a file descriptor object/handle opened 
                   for reading or a string indicating a filepath that 
                   can be opened for reading using open().    
        `format` - file format specification               
    """
    reader = get_reader(format)
    return reader.read_trees(source_file_handle(file=file))
    
def trees_from_string(string, format):
    """
    Returns a *list* of TreesBlock objects parsed from the source, where:
        `string` - a string containing the data to be parsed.   
        `format` - file format specification               
    """
    reader = get_reader(format)
    return reader.read_trees(source_file_handle(string=string))     
    
def get_nexus(file=None, string=None):
    """
    Returns a Dataset object parsed from a NEXUS or NEWICK source.
        `file`   - can either be a file descriptor object/handle opened 
                   for reading or a string indicating a filepath that 
                   can be opened for reading using open().
        `string` - a string containing the data to be parsed.
    Either `file` or `string` must be given. If both are given, `file` is used.                
    """
    return nexus.read_dataset(source_file_handle(file=file, string=string))    
    
############################################################################
## Wrappers (Writing)    

def store_dataset(dataset, format, dest=None):
    """
    Writes the Dataset object `dataset` using `writer` (a DatasetWriter or 
    derived object) to `dest`. If `dest` is a string, then it is assumed to be
    a path name, and open() is used to construct an output stream handle from it.
    If `dest` is not given, then the dataset is written to a string and a string 
    is returned.
    """
    writer = get_writer(format)
    if dest is None:
        dest = StringIO.StringIO()
    if isinstance(dest, str):
        dest = open(dest, "w")
    writer.write_dataset(dataset, dest)
    if hasattr(dest, "getvalue"):
        return dest.getvalue()

def store_trees(trees_collection, format, dest=None):
    """
    Writes the list of trees `trees` to `dest` using writer.
    """
    if isinstance(trees_collection, TreesBlock):
        trees_block = trees_collection
    else:
        trees_block = TreesBlock()
        for tree in trees_collection:
            trees_block.append(tree)
        trees_block.normalize_taxa()
    dataset = Dataset()
    dataset.add_trees_block(trees_block=trees_block)
    return store_dataset(dataset=dataset,
        format=format,                  
        dest=dest)
                  
def store_chars(char_block, format, dest=None):
    """
    Writes the CharacterBlock `char_block` to `dest` using writer.
    """
    dataset = Dataset()
    dataset.add_char_block(char_block=char_block)
    return store_dataset(dataset=dataset,
        format=format,                  
        dest=dest)                  

############################################################################
## Helpers

def source_file_handle(file=None, string=None):
    """
    Construct an appropriate file handle (i.e. something that supports read()
    operations) based on the given arguments.
    """
    if file is None and string is None:
        raise Exception("File or string source must be specified.")            
    if file is not None:        
        if isinstance(file, str):
            file = open(file, "r")        
        return file
    else:
        return StringIO.StringIO(string)
        
def get_writer(format):
    """
    Return reader of the appropriate format.
    """
    format = format.upper()
    if format not in WRITERS:
        raise Exception('Unrecognized format specificiation "%s", ' \
            'must be one of: %s' % (format,
             ", ".join([('"'+f+'"') for f in WRITERS]),
             ))
    return WRITERS[format]()      
    
def get_reader(format):
    """
    Return reader of the appropriate format.
    """
    format = format.upper()
    if format not in READERS:
        raise Exception('Unrecognized format specificiation "%s", ' \
            'must be one of: %s' % (format,
             ", ".join([('"'+f+'"') for f in READERS]),
             ))
    return READERS[format]()            
    