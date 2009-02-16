#! /usr/bin/env python

############################################################################
##  nexus.py
##
##  Part of the DendroPy library for phylogenetic computing.
##
##  Copyright 2007 Jeet Sukumaran and Mark T. Holder.
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
This module wraps routines needed for reading and writing trees (and data) in
NEXUS format. Note that the current parser supports a SINGLE taxa block / 
character block / data block / trees block model. Behavior with multiple taxa 
blocks, data blocks, trees blocks etc. is undefined.
"""

import re
import os
import sys
import StringIO

from dendropy import datasets
from dendropy import taxa
from dendropy import trees
from dendropy import characters   

############################################################################
## Standard Tree Iterator
      
def iterate_over_trees(file_obj=None, taxa_block=None):
    """
    Generator to iterate over trees in data file.
    Primary goal is to be memory efficient, storing no more than one tree
    at a time. Speed might have to be sacrificed for this!
    """
    if taxa_block is not None:
        taxa_block = taxa_block
    else:        
        taxa_block = taxa.TaxaBlock()
    stream_tokenizer = NexusStreamTokenizer(file_obj)
    token = stream_tokenizer.read_next_token_ucase()
    if token == "#NEXUS":
        file_format = "NEXUS"
        nexus_reader = NexusReader()
        nexus_reader.stream_tokenizer = stream_tokenizer
        while not nexus_reader.stream_tokenizer.eof:
            token = nexus_reader.stream_tokenizer.read_next_token_ucase()
            while token != None and token != 'BEGIN' and not nexus_reader.stream_tokenizer.eof:
                token = nexus_reader.stream_tokenizer.read_next_token_ucase()
            token = nexus_reader.stream_tokenizer.read_next_token_ucase()
            if token == 'TREES':
                nexus_reader.stream_tokenizer.skip_to_semicolon() # move past BEGIN command
                while not (token == 'END' or token == 'ENDBLOCK') \
                    and not nexus_reader.stream_tokenizer.eof \
                    and not token==None:
                    token = nexus_reader.stream_tokenizer.read_next_token_ucase()
                    if token == 'TRANSLATE':
                        nexus_reader.parse_translate_statement()
                    if token == 'TREE':
                        tree = nexus_reader.parse_tree_statement(taxa_block)
                        yield tree
                nexus_reader.stream_tokenizer.skip_to_semicolon() # move past END command
            else:
                # unknown block
                while not (token == 'END' or token == 'ENDBLOCK') \
                    and not nexus_reader.stream_tokenizer.eof \
                    and not token==None:
                    #print token
                    nexus_reader.stream_tokenizer.skip_to_semicolon()
                    token = nexus_reader.stream_tokenizer.read_next_token_ucase()

    else:
        stream_tokenizer.stream_handle.seek(0)
        while not stream_tokenizer.eof:
            tree = parse_newick_tree_stream(stream_tokenizer=stream_tokenizer, 
                                                 taxa_block=taxa_block, 
                                                 translate_dict=None) 
            if tree:
                yield tree
                                                 
############################################################################
## Universal Nex-ish Readers

def read_dataset(file_obj, dataset=None):
    """
    Note: due to usage of seek(), does not work on stream sources 
    (such as stdin). In this case, client must either buffer stream to string
    (e.g. file_obj=StringIO.StringIO(sys.stdin.read())) or use direct methods.
    """
    stream_tokenizer = NexusStreamTokenizer(file_obj)
    token = stream_tokenizer.read_next_token_ucase()
    stream_tokenizer.stream_handle.seek(0)
    if token == "#NEXUS":
        reader = NexusReader()
    else: # assume NEWICK
        reader = NewickReader()
    return reader.read_dataset(file_obj=file_obj, dataset=dataset)

def read_trees(file_obj, dataset=None):
    dataset = read_dataset(file_obj=file_obj, dataset=dataset)
    return dataset.trees_blocks

############################################################################
## support functions

def split_to_newick(split, taxa_block):
    """
    Represents a split as a newick string.
    """
    taxlabels = taxa_block.labels()
    
    # do not do the root
    if split == 0 or (split == taxa_block.all_taxa_bitmask()):
        return "(%s)" % (",".join(taxlabels))
    
    idx = 0
    left = []
    right = []
    while split >= 0 and idx < len(taxlabels):
        if split & 1:
            left.append(taxlabels[idx])
        else:
            right.append(taxlabels[idx])
        idx += 1
        split = split >> 1
    assert ( len(left) + len(right) ) == len(taxlabels)
    return "((%s), (%s))" % (", ".join(left), ", ".join(right))

def _parse_taxon_label(token, stream_tokenizer):
    if not stream_tokenizer.quoted_token and token.count("_"):
        taxlabel = token.replace("_", " ")
    else:
        taxlabel = token
    return taxlabel 

def map_to_iupac_ambiguity_code(states):
    """
    Given a sequence of characters, maps ambiguities given the form of
    `AG` to IUPAC codes (e.g., `AC -> R').
    """
    if len(states) == 1:
        return states[0]
    states = [state.upper() for state in states]
    if states.count('A') and states.count('C') and states.count('G') and (states.count('T') or states.count('U')):
        return 'N'
    if states.count('A') and states.count('C') and states.count('G'):
        return 'V'
    if states.count('A') and states.count('C') and (states.count('T') or states.count('U')):
        return 'H'
    if states.count('A') and states.count('G') and (states.count('T') or states.count('U')):
        return 'D'
    if states.count('C') and states.count('G') and (states.count('T') or states.count('U')):
        return 'B'
    if states.count('A') and states.count('C'):
        return 'M'
    if states.count('A') and states.count('G'):
        return 'R'
    if states.count('C') and (states.count('T') or states.count('U')):
        return 'W'
    if states.count('C') and states.count('G'):
        return 'S'
    if states.count('C') and (states.count('T') or states.count('U')):
        return 'Y'
    if states.count('G') and (states.count('T') or states.count('U')):
        return 'K'
    raise Exception('Unrecognized characters in "%s"' % states)

def parse_sequence_iupac_ambiguities(seq):
    """
    Given a sequence of characters, with ambiguities denoted by
    `{<STATES>}`, this returns a sequence of characters with the
    ambiguities mapped to the IUPAC codes.
    """
    if isinstance(seq, list):
      as_list = True
      seq = ''.join(seq)
    else:
      as_list = False
    result = ""
    pattern = re.compile('{(.*?)}')
    pos = 0
    match = pattern.search(seq, pos)
    if match:
        while match:
          if pos > 0:
            result = result + seq[pos-1:match.start()]
          else:
            result = result + seq[pos:match.start()]
          result = result + map_to_iupac_ambiguity_code(match.group(1))
          pos = match.end() + 1
          if pos < len(seq) - 1:
            match = pattern.search(seq, pos)
          else:
            match = None
        result = result + seq[pos-1:]
    else:
      return seq
    if as_list:
      return [char for char in result]
    else:
      return result
      
############################################################################
##  Fundamental NEWICK Tree parsers

def parse_newick_string(tree_statement, taxa_block=None, translate_dict=None):
    "Processes a (SINGLE) TREE statement string."
    stream_handle = StringIO.StringIO(tree_statement)
    stream_tokenizer = NexusStreamTokenizer(stream_handle)
    tree = parse_newick_tree_stream(stream_tokenizer=stream_tokenizer, 
                                     taxa_block=taxa_block,
                                     translate_dict=translate_dict)
    return tree    
    
def parse_newick_tree_stream(stream_tokenizer, taxa_block=None, translate_dict=None):
    """
    Processes a (SINGLE) TREE statement. Assumes that the input stream is
    located at the beginning of the statement (i.e., the first
    parenthesis that defines the tree).
    """    
    token = stream_tokenizer.read_next_token()
    if not token:
        return None    
    tree = trees.Tree()
    if taxa_block is None:
        taxa_block = taxa.TaxaBlock()    
    tree.taxa_block = taxa_block
    child_nodes = []    
    while token and token != ';' and token != ':':        
        # process nodes until no more tokens, end of tree
        # statement, or ':' is encountered, presumably outside
        # main tree parenthetical statement (i.e., length of root
        node = parse_newick_node_stream(stream_tokenizer, tree)
        if node:
            child_nodes.append(node)
        token = stream_tokenizer.current_token
        if stream_tokenizer.current_token == ')':
            # OK, I'll be the first to admit that this is rather
            # hacky but it works.
            # If an end-parenthesis is encountered ...
            token = stream_tokenizer.read_next_token()
            if token and not token in NexusStreamTokenizer.punctuation:
                break
    for node in child_nodes:
        tree.seed_node.add_child(node)
    if token and not token in NexusStreamTokenizer.punctuation:
        tree.seed_node.label = _parse_taxon_label(token, stream_tokenizer)
        token = stream_tokenizer.read_next_token()
    if token and token == ':':
        length = stream_tokenizer.read_next_token(ignore_punctuation='-')
        tree.seed_node.edge.length = length
        
    # convert labels at terminal nodes to taxa
    for node in tree.leaf_nodes():
        if node.label:
            if translate_dict and node.label in translate_dict:
                label = translate_dict[node.label]
            else:
                label = node.label                      
            node.taxon = taxa_block.get_taxon(label=label)
    return tree

def parse_newick_node_stream(stream_tokenizer, tree):
    """
    Processes a TREE statement. Assumes that the file reader is
    positioned right after the '(' token in a TREE statement or
    right after a comma following a node inside a tree statement.
    """
    node = trees.Node()
    token = stream_tokenizer.read_next_token()
    while token and token != ')' and token != ',' and token != ";":  
        if token=="." or token not in NexusStreamTokenizer.punctuation:
            if node.label is None:
                node.label = _parse_taxon_label(token, stream_tokenizer)
            else:                    
                node.label = node.label + _parse_taxon_label(token, stream_tokenizer)
        if token == ':':
            edge_length_str = stream_tokenizer.read_next_token(ignore_punctuation='-')
            try:
                node.edge.length = float(edge_length_str)
            except ValueError:
                node.edge.length = edge_length_str
        if token == '(':
            while token and token != ')':
                child_node = parse_newick_node_stream(stream_tokenizer, tree)
                if child_node:
                    node.add_child(child_node)
                token = stream_tokenizer.current_token                  
        token = stream_tokenizer.read_next_token()    
    return node     
        
     
############################################################################
## CLASS: NexusStreamTokenizer

class NexusStreamTokenizer(object):
    "Encapsulates reading NEXUS/NEWICK tokens from file."

    #######################################################################
    ## STATIC METHODS

    punctuation = '\(\)\[\]\{\}\\\/\,\;\:\=\*\'\"\`\+\-\<\>'
    whitespace = ' \0\t\n\r'

    def is_whitespace(char):
        return char in NexusStreamTokenizer.whitespace

    is_whitespace = staticmethod(is_whitespace)

    def has_whitespace(s):
        return re.search('['+NexusStreamTokenizer.whitespace+']', s) != None

    has_whitespace = staticmethod(has_whitespace)

    def is_punctuation(char):
        if char:
            return char in NexusStreamTokenizer.punctuation

    is_punctuation = staticmethod(is_punctuation)

    def has_punctuation(s):
        return re.search('['+NexusStreamTokenizer.punctuation+']', s) != None

    has_punctuation = staticmethod(has_punctuation)

    def is_whitespace_or_punctuation(char):
        return NexusStreamTokenizer.is_whitespace(char) or NexusStreamTokenizer.is_punctuation(char)

    is_whitespace_or_punctuation = staticmethod(is_whitespace_or_punctuation)

    def has_whitespace_or_punctuation(s):
        return NexusStreamTokenizer.has_whitespace(s) or NexusStreamTokenizer.has_punctuation(s)

    has_whitespace_or_punctuation = staticmethod(has_whitespace_or_punctuation)

    def validate_identifier(label):
        if NexusStreamTokenizer.has_whitespace_or_punctuation(label):
            if (label[0] == "'" and label[1] == "'") or label[0] != "'":
                label = "'" + label
            if (label[-1] == "'" and label[-2] == "'") or label[-1] != "'":
                label = label + "'"
            return label
        else:
            return label

    validate_identifier = staticmethod(validate_identifier)

    #######################################################################
    ## NESTED CLASSES

    class SyntaxException(Exception):

        def __init__(self, row, column, message):
            self.row = row
            self.column = column
            self.message = message

        def __str__(self):
            return 'ERROR PARSING FILE IN LINE %d: %s' % (self.row, self.message)

    #######################################################################
    ## INSTANCE METHODS

    def __init__(self, stream_handle=None):
        self.reset()
        if stream_handle:
            self.stream_handle = stream_handle
            
    def reset(self):
        self.quoted_token = False
        self.stream_handle = None
        self.current_file_char = None
        self.current_token = None
        self.eof = False
        self.current_line_number = 1
        self.current_col_number = 1
        self.previous_file_char = None

    def _get_current_file_char(self):
        "Returns the current character from the file stream."
        if self.__current_file_char == None:
            self.__current_file_char = self.read_next_char()
        return self.__current_file_char

    def _set_current_file_char(self, new_char):
        self.__current_file_char = new_char

    current_file_char = property(_get_current_file_char, _set_current_file_char)

    def read_next_char(self):
        """
        Advances the file stream cursor to the next character and returns
        it.
        """
        if self.stream_handle:
            read_char = self.stream_handle.read(1) # returns empty string if EOF
            if read_char == '':
                self.eof = True
            else:
                if self.previous_file_char == '\n':
                    self.current_line_number = self.current_line_number + 1
                    self.current_col_number = 0
                self.previous_file_char = self.__current_file_char
                self.current_col_number = self.current_col_number + 1
            self.current_file_char = read_char
            return self.__current_file_char
        else:
            return None

    def skip_comment(self):
        """
        Reads characters from the file until current comment block (and
        any nested comment block terminates. Assumes current cursor
        position is on first character inside comment block.
        """
        while self.current_file_char != ']' and not self.eof:
            if self.read_next_char() == '[':
                self.skip_comment()
        self.read_next_char()

    def read_noncomment_character(self):
        """
        Gets the first character outside a comment block from the
        current file stream position, inclusive.
        """
        if self.current_file_char == '[':
            self.skip_comment()
        return self.current_file_char
    noncomment_file_char = property(read_noncomment_character)

    def skip_to_significant_character(self):
        "Advances to the first non-whitespace character outside a comment block."
        while (NexusStreamTokenizer.is_whitespace(self.current_file_char) or self.current_file_char=='[') and not self.eof:
            if self.current_file_char=='[':
                self.read_noncomment_character()
            else:
                self.read_next_char()
        return self.current_file_char

    def read_next_token(self, ignore_punctuation=None, preserve_quotes=False):
        """
        Reads the next token in the file stream. A token in this context is any word or punctuation character
        outside of a comment block.
        """
        if ignore_punctuation == None:
            ignore_punctuation = []
        if not self.eof:
            token = ''
            self.skip_to_significant_character()
            if not self.eof:
                if self.current_file_char == "'":
                    self.read_next_char()
                    self.quoted_token = True
                    end_quote = False
                    while not end_quote and not self.eof:
                        if self.current_file_char == "'":
                            self.read_next_char()
                            if self.current_file_char == "'":
                                token = token + "'"
                                self.read_next_char()
                            else:
                                end_quote = True
                        else:
                            token = token + self.current_file_char
                            self.read_next_char()
                    if preserve_quotes:
                        token = "'" + token + "'"
                else:
                    self.quoted_token = False
                    if NexusStreamTokenizer.is_punctuation(self.current_file_char) and self.current_file_char not in ignore_punctuation:
                        token = self.current_file_char
                        self.read_next_char()
                    else:
                        while not self.eof and (not NexusStreamTokenizer.is_whitespace_or_punctuation(self.current_file_char) or self.current_file_char in ignore_punctuation):
                            token = token + self.current_file_char
                            self.read_next_char()
                self.current_token = token
            else:
                self.current_token = None
        else:
            self.current_token = None
        return self.current_token

    def read_next_token_ucase(self, ignore_punctuation=[]):
        """
        Reads the next token in the file stream, upper-casing it
        before returning it.
        """
        t = self.read_next_token(ignore_punctuation=ignore_punctuation)
        if t != None:
            return t.upper()
        else:
            return None

    def skip_to_semicolon(self):
        "Advances the file stream cursor to the next semi-colon."
        token = self.read_next_token()
        while token != ';' and not self.eof and token != None:
            token = self.read_next_token()
            pass

############################################################################
## CLASS: NexusReader

class NexusReader(datasets.Reader):
    "Encapsulates loading and parsing of a NEXUS format file."

    class NotNexusFileException(NexusStreamTokenizer.SyntaxException):
        def __init__(self, filepath, row, column, message):
            NexusStreamTokenizer.SyntaxException.__init__(self, \
                filepath, 
                row, 
                column, 
                message)

    def __init__(self):
        datasets.Reader.__init__(self)
        self.stream_tokenizer = NexusStreamTokenizer()
        self.reset()

    def reset(self):
        self.dataset = datasets.Dataset()
        self.char_block_type = characters.StandardCharactersBlock
        self.interleave = False
        self.symbols = "012"
        self.gap_char = '-'
        self.missing_char = '?'
        self.match_char = '.'
        self.tree_translate_dict = {}

    def read_dataset(self, file_obj, dataset=None):
        """
        Instantiates and returns a DataSet object based on the
        NEXUS-formatted contents read from the file descriptor object
        `file_obj`.
        """
        #self.reset()
        self.stream_tokenizer = NexusStreamTokenizer()
        self.stream_tokenizer.stream_handle = file_obj
        return self.parse_nexus_file(dataset)

    ## Class-specific ##

    def parse_nexus_file(self, dataset=None):
        "Main file parsing driver."
        self.reset()
        if dataset is not None:
            self.dataset = dataset
        token = self.stream_tokenizer.read_next_token_ucase()
        if token != "#NEXUS":
            raise self.syntax_exception('Expecting "#NEXUS", but found "%s"' % token)
        else:
            while not self.stream_tokenizer.eof:
                token = self.stream_tokenizer.read_next_token_ucase()
                while token != None and token != 'BEGIN' and not self.stream_tokenizer.eof:
                    token = self.stream_tokenizer.read_next_token_ucase()
                token = self.stream_tokenizer.read_next_token_ucase()
                if token == 'TAXA':
                    self.stream_tokenizer.skip_to_semicolon() # move past BEGIN statement
                    while not (token == 'END' or token == 'ENDBLOCK') \
                        and not self.stream_tokenizer.eof \
                        and not token==None:
                        token = self.stream_tokenizer.read_next_token_ucase()
                        if token == 'DIMENSIONS':
                            self.parse_dimensions_statement()
                        if token == 'TAXLABELS':
                            self.parse_taxlabels_statement()
                    self.stream_tokenizer.skip_to_semicolon() # move past END statement
                elif token == 'CHARACTERS':
                    if self.include_characters:
                        self.stream_tokenizer.skip_to_semicolon() # move past BEGIN command
                        while not (token == 'END' or token == 'ENDBLOCK') \
                            and not self.stream_tokenizer.eof \
                            and not token==None:
                            token = self.stream_tokenizer.read_next_token_ucase()
                            if token == 'DIMENSIONS':
                                self.parse_dimensions_statement()
                            if token == 'FORMAT':
                                self.parse_format_statement()
                            if token == 'MATRIX':
                                self.parse_matrix_statement()
                        self.stream_tokenizer.skip_to_semicolon() # move past END command
                    else:
                        token = self.consume_to_end_of_block(token)
                elif token == 'DATA':
                    self.stream_tokenizer.skip_to_semicolon() # move past BEGIN command
                    while not (token == 'END' or token == 'ENDBLOCK') \
                        and not self.stream_tokenizer.eof \
                        and not token==None:
                        token = self.stream_tokenizer.read_next_token_ucase()
                        if token == 'DIMENSIONS':
                            self.parse_dimensions_statement()
                        if token == 'FORMAT':
                            self.parse_format_statement()
                        if token == 'MATRIX':
                            self.parse_matrix_statement()
                    self.stream_tokenizer.skip_to_semicolon() # move past END command
                elif token == 'TREES':
                    if self.include_trees:
                        trees_block = trees.TreesBlock()
                        trees_block.taxa_block = self.get_default_taxa_block()
                        self.dataset.add_trees_block(trees_block=trees_block)
                        self.stream_tokenizer.skip_to_semicolon() # move past BEGIN command
                        while not (token == 'END' or token == 'ENDBLOCK') \
                            and not self.stream_tokenizer.eof \
                            and not token==None:
                            token = self.stream_tokenizer.read_next_token_ucase()
                            if token == 'TRANSLATE':
                                self.parse_translate_statement()
                            if token == 'TREE':
                                tree = self.parse_tree_statement(trees_block.taxa_block)
                                trees_block.append(tree)
                        self.stream_tokenizer.skip_to_semicolon() # move past END command
                    else:
                        token = self.consume_to_end_of_block(token)
                else:
                    # unknown block
                    token = self.consume_to_end_of_block(token)

        return self.dataset

    def consume_to_end_of_block(self, token):
        while not (token == 'END' or token == 'ENDBLOCK') \
            and not self.stream_tokenizer.eof \
            and not token==None:
            self.stream_tokenizer.skip_to_semicolon()
            token = self.stream_tokenizer.read_next_token_ucase()
        return token            
        
    def syntax_exception(self, message):
        """
        Returns an exception object parameterized with line and
        column number values.
        """
        return NexusStreamTokenizer.SyntaxException(self.stream_tokenizer.current_line_number, 
                                                    self.stream_tokenizer.current_col_number, message)

    def parse_format_statement(self):
        """
        Processes a FORMAT command. Assumes that the file reader is
        positioned right after the "FORMAT" token in a FORMAT command.
        """
        token = self.stream_tokenizer.read_next_token_ucase()
        while token != ';':
            #print token
            if token == 'DATATYPE':
                token = self.stream_tokenizer.read_next_token_ucase()
                if token == '=':
                    token = self.stream_tokenizer.read_next_token_ucase()
                    if token == "DNA" or token == "NUCLEOTIDES":
                        self.char_block_type = characters.DnaCharactersBlock
                    elif token == "RNA":
                        self.char_block_type = characters.RnaCharactersBlock
                    elif token == "PROTEIN":
                        self.char_block_type = characters.ProteinCharactersBlock
                    else:                        
                        # defaults to STANDARD elif token == "STANDARD":
                        self.char_block_type = characters.StandardCharactersBlock
                        self.symbols = "12"
                else:
                    raise self.syntax_exception('Expecting "=" after DATATYPE keyword')
            elif token == 'SYMBOLS':
                token = self.stream_tokenizer.read_next_token_ucase()
                if token == '=':
                    token = self.stream_tokenizer.read_next_token_ucase()
                    if token == '"':
                        self.symbols = ""
                        token = self.stream_tokenizer.read_next_token_ucase()
                        while token != '"':
                            if token not in self.symbols:
                                self.symbols = self.symbols + token
                            token = self.stream_tokenizer.read_next_token_ucase()
                    else:
                        raise self.syntax_exception('Expecting \'"\' before beginning SYMBOLS list')
                else:
                    raise self.syntax_exception('Expecting "=" after SYMBOLS keyword')
            elif token == 'GAP':
                token = self.stream_tokenizer.read_next_token_ucase()
                if token == '=':
                    token = self.stream_tokenizer.read_next_token_ucase()
                    self.gap_char = token
                else:
                    raise self.syntax_exception('Expecting "=" after GAP keyword')
            elif token == 'INTERLEAVE':
                token = self.stream_tokenizer.read_next_token_ucase()
                if token == '=':
                    token = self.stream_tokenizer.read_next_token_ucase()
                    if token.upper().startswith("N"):
                        self.interleave = False
                    else:
                        self.interleave = True
                else:
                    self.interleave = True                    
            elif token == 'MISSING':
                token = self.stream_tokenizer.read_next_token_ucase()
                if token == '=':
                    token = self.stream_tokenizer.read_next_token_ucase()
                    self.missing_char = token
                else:
                    raise self.syntax_exception('Expecting "=" after MISSING keyword')
            elif token == 'MATCHCHAR':
                token = self.stream_tokenizer.read_next_token_ucase()
                if token == '=':
                    token = self.stream_tokenizer.read_next_token_ucase()
                    self.match_char = token
                else:
                    raise self.syntax_exception('Expecting "=" after MISSING keyword')
            token = self.stream_tokenizer.read_next_token_ucase()
         
    def parse_tree_statement(self, taxa_block):
        """
        Processes a TREE command. Assumes that the file reader is
        positioned right after the "TREE" token in a TREE command.
        Calls on the NewickStatementParser of the trees module.
        """
        token = self.stream_tokenizer.read_next_token()
        if token == '*':
            token = self.stream_tokenizer.read_next_token()
        tree_name = token
        token = self.stream_tokenizer.read_next_token()
        if token != '=':
            raise self.syntax_exception('Expecting "=" in definition of Tree "%s" but found "%s"' % (tree_name, token))
        else:
            # collect entire tree statement by accumulating tokens until we reach a semi-colon
#             statement = []
#             token = self.stream_tokenizer.read_next_token(preserve_quotes=True)
#             while token and token != ';':
#                 statement.append(token)
#                 token = self.stream_tokenizer.read_next_token(preserve_quotes=True)
#             newick_parser = NewickTreeParser()
            tree = parse_newick_tree_stream(stream_tokenizer=self.stream_tokenizer,
                                            taxa_block=taxa_block,
                                            translate_dict=self.tree_translate_dict)
            tree.label = tree_name
        if self.stream_tokenizer.current_token != ';':
            self.stream_tokenizer.skip_to_semicolon()
        return tree

    def parse_translate_statement(self):
        """
        Processes a TRANSLATE command. Assumes that the file reader is
        positioned right after the "TRANSLATE" token in a TRANSLATE command.
        """
        token = self.stream_tokenizer.current_token
        while token and token != ';':
            translation_token = self.stream_tokenizer.read_next_token()
            translation_label = self.stream_tokenizer.read_next_token()
            token = self.stream_tokenizer.read_next_token() # ","
            #print translation_token, translation_label, token
            if token != ',' and token != ';':
                raise self.syntax_exception('Expecting "," in TRANSLATE statement after definition for %s = "%s", but found "%s" instead' % (translation_token, translation_label, token))
            else:
                self.tree_translate_dict[translation_token] = translation_label

    def parse_dimensions_statement(self):
        """
        Processes a DIMENSIONS command. Assumes that the file reader is
        positioned right after the "DIMENSIONS" token in a DIMENSIONS command.
        """
        token = self.stream_tokenizer.read_next_token_ucase()
        while token != ';':
            #print token
            if token == 'NTAX':
                token = self.stream_tokenizer.read_next_token_ucase()
                if token == '=':
                    token = self.stream_tokenizer.read_next_token_ucase()
                    if token.isdigit():
                        self.file_specified_ntax = int(token)
                    else:
                        raise self.syntax_exception('Expecting numeric value for NTAX')
                else:
                    raise self.syntax_exception('Expecting "=" after NTAX keyword')
            elif token == 'NCHAR':
                token = self.stream_tokenizer.read_next_token_ucase()
                if token == '=':
                    token = self.stream_tokenizer.read_next_token_ucase()
                    if token.isdigit():
                        self.file_specified_nchar = int(token)
                    else:
                        raise self.syntax_exception('Expecting numeric value for NCHAR')
                else:
                    raise self.syntax_exception('Expecting "=" after NCHAR keyword')
            token = self.stream_tokenizer.read_next_token_ucase()

    def get_default_taxa_block(self, taxa_block=None):
        if taxa_block is None:
            if len(self.dataset.taxa_blocks) == 0:
                taxa_block = taxa.TaxaBlock()
                self.dataset.add_taxa_block(taxa_block=taxa_block)
            else:
                taxa_block = self.dataset.taxa_blocks[0]
        else:
            if taxa_block not in self.dataset.taxa_blocks:
                self.dataset.taxa_blocks.insert(taxa_block)
        return taxa_block                          
          
    def parse_taxlabels_statement(self, taxa_block=None):
        """
        Processes a TAXLABELS command. Assumes that the file reader is
        positioned right after the "TAXLABELS" token in a TAXLABELS command.
        """
        taxa_block = self.get_default_taxa_block(taxa_block)                
        token = self.stream_tokenizer.read_next_token()
        while token != ';':
            taxa_block.add_taxon(label=_parse_taxon_label(token, self.stream_tokenizer))        
            token = self.stream_tokenizer.read_next_token()

    def build_state_alphabet(self, char_block, symbols):
        sa = characters.StateAlphabet()
        for symbol in symbols:
            sa.append(characters.StateAlphabetElement(symbol=symbol))
        if self.missing_char:
            sa.append(characters.StateAlphabetElement(symbol=self.missing_char,
                                           multistate=characters.StateAlphabetElement.AMBIGUOUS_STATE,
                                           member_states=sa.get_states(symbols=symbols)))
        char_block.state_alphabets = [sa]
        char_block.default_state_alphabet = char_block.state_alphabets[0]
        return char_block

    def parse_matrix_statement(self, taxa_block=None):
        """
        Processes a MATRIX command. Assumes that the file reader
        is positioned right after the "MATRIX" token in a MATRIX command,
        and that NTAX and NCHAR have been specified accurately.
        """
        taxa_block = self.get_default_taxa_block(taxa_block)
        if not self.file_specified_ntax:
            raise self.syntax_exception('NTAX must be defined by DIMENSIONS command to non-zero value before MATRIX command')
        elif not self.file_specified_nchar:
            raise self.syntax_exception('NCHAR must be defined by DIMENSIONS command to non-zero value before MATRIX command')
        else:
            char_block = self.char_block_type()
            char_block.taxa_block = taxa_block
            if isinstance(char_block, characters.StandardCharactersBlock):
                char_block = self.build_state_alphabet(char_block, self.symbols)
            self.dataset.add_char_block(char_block=char_block)
            symbol_state_map = char_block.default_state_alphabet.symbol_state_map()
            if True: # future: trap and handle no labels, transpose etc.
                token = self.stream_tokenizer.read_next_token()
                while token != ';' and not self.stream_tokenizer.eof:
                    taxon = taxa_block.get_taxon(label=_parse_taxon_label(token, self.stream_tokenizer))
                    if taxon not in char_block:
                        if self.include_characters:
                            char_block[taxon] = characters.CharacterDataVector(taxon=taxon)
                    if self.interleave:
                        while self.stream_tokenizer.current_file_char != '\n' and self.stream_tokenizer.current_file_char != '\r':
                            if self.stream_tokenizer.current_file_char not in [' ', '\t'] and self.include_characters:
                                state = symbol_state_map[self.stream_tokenizer.current_file_char]
                                char_block[taxon].append(characters.CharacterDataCell(value=state))
                            self.stream_tokenizer.read_next_char()
                    else:
                        while len(char_block[taxon]) < self.file_specified_nchar and not self.stream_tokenizer.eof:
                            char_group = self.stream_tokenizer.read_next_token()
                            if self.include_characters:
                                char_group = parse_sequence_iupac_ambiguities(char_group)
                                for char in char_group:
                                    state = symbol_state_map[char]
                                    char_block[taxon].append(characters.CharacterDataCell(value=state))
                    token = self.stream_tokenizer.read_next_token()
            else:
                ## TODO: NO LABELS/TRANSPOSED ##
                pass
                
                
############################################################################
## CLASS: NexusWriter

class NexusWriter(datasets.Writer):
    "Implements the DataWriter interface for handling NEXML files."

    def __init__(self, simple=False):
        "Calls the base class constructor."
        datasets.Writer.__init__(self)
        self.simple = simple
        self.write_rooting = True
        self.comment = []

    def compose_taxlabel(label):
        if NexusStreamTokenizer.has_whitespace(label) or NexusStreamTokenizer.has_punctuation(label):
            return "'" + label + "'"
        else:
            return label
    compose_taxlabel = staticmethod(compose_taxlabel)

    def write_dataset(self, dataset, dest):
        """
        Writes dataset to a full NEXUS
        document.
        """
        dest.write('#NEXUS\n\n')

        if self.comment is not None:
            if isinstance(self.comment, list):
                for line in self.comment:
                    if line.strip().replace("\n", "").replace("\r", ""):
                        dest.write("[ %s ]\n" % line)
                    else:
                        dest.write("\n")
                dest.write("\n")
            else:
                dest.write("[ %s ]\n\n" % self.comment)
        if (dataset.char_blocks or dataset.trees_blocks) and not self.simple:
            self.write_taxa_block(taxa_block=dataset.taxa_blocks[0], dest=dest)
        if dataset.char_blocks:
            self.write_char_block(char_block=dataset.char_blocks[0], dest=dest, simple_nexus=self.simple)
        if dataset.trees_blocks:
            self.write_trees_block(trees_block=dataset.trees_blocks[0], dest=dest)

    def write_trees_block(self, trees_block, dest):
        block = []
        newick_writer = NewickWriter()
        block.append('BEGIN TREES;')
        for treeidx, tree in enumerate(trees_block):
            if tree.label:
                tree_name = tree.label
            else:
                tree_name = str(treeidx)
            newick_str = newick_writer.compose_node(tree.seed_node)
            if tree.is_rooted and self.write_rooting:
                rooting = "[&R] "
            elif not tree.is_rooted and self.write_rooting:
                rooting = "[&U] "
            else:
                rooting = ""
            block.append('    tree %s = %s%s;' % (tree_name, rooting, newick_str))
        block.append('END;\n\n')
        dest.write('\n'.join(block))

    def write_taxa_block(self, taxa_block, dest):
        block = []
        block.append('BEGIN TAXA;')
        block.append('    DIMENSIONS NTAX=%d;' % len(taxa_block))
        block.append('    TAXLABELS')
        for taxon in taxa_block:
            block.append('        %s' % self.compose_taxlabel(taxon.label))
        block.append('  ;')
        block.append('END;\n\n')
        dest.write('\n'.join(block))

    def compose_format_terms(self, char_block):
        format = []
        if isinstance(char_block, characters.DnaCharactersBlock):
            format.append("DATATYPE=DNA")
        elif isinstance(char_block, characters.RnaCharactersBlock):
            format.append("DATATYPE=RNA")
        elif isinstance(char_block, characters.ProteinCharactersBlock):
            format.append("DATATYPE=PROTEIN")
        else:
            format.append("DATATYPE=STANDARD")
            format.append('SYMBOLS="%s"' % ''.join([str(a) for a in char_block.default_state_alphabet]))
        format.append("GAP=- MISSING=? MATCHCHAR=.")
        return ' '.join(format)

    def write_char_block(self, char_block, dest, simple_nexus=False):
        nexus = []
        taxlabels = [taxon.label for taxon in char_block]
        max_label_len = max([len(label) for label in taxlabels])
        nchar = max([len(seq) for seq in char_block.values()])
        if simple_nexus:
            nexus.append('BEGIN DATA;')
            ntaxstr = "NTAX=%d" % len(taxlabels)
        else:
            nexus.append('BEGIN CHARACTERS;')
            ntaxstr = ""
        nexus.append('    DIMENSIONS %s NCHAR=%d;' % (ntaxstr, nchar))
        nexus.append('    FORMAT %s;' % self.compose_format_terms(char_block))
        nexus.append('    MATRIX')
        taxa = char_block.keys()
        taxa.sort()
        for taxon in taxa:
            seq_vec = char_block[taxon]
            #print t
            seq = ''.join([str(seq_sym) for seq_sym in seq_vec])
#             seq.replace('~','-')
            seq = seq.ljust(nchar, '-')
            nexus.append('%s    %s' % (self.compose_taxlabel(taxon.label).ljust(max_label_len), seq))
        nexus.append('    ;')
        nexus.append('END;\n\n')
        dest.write('\n'.join(nexus))
                
############################################################################
## CLASS: NewickReader        
        
class NewickReader(datasets.Reader):
    "Implementation of TreeReader for NEWICK files and strings."
    
    def __init__(self):
        """
        This has changed so much so many times that any documentation
        I put in here will probably be obselete in a matter of hours
        so this comment is all you are getting.
        """
        datasets.Reader.__init__(self)
        
    def read_dataset(self, file_obj, dataset=None):
        """
        Instantiates and returns a DataSet object based on the
        NEWICK-formatted contents read from the file descriptor object
        `file_obj`.
        """
        taxa_block = None
        need_to_add_taxa = True
        if dataset is None:
            dataset = datasets.Dataset()
        elif len(dataset.taxa_blocks) == 1:
            taxa_block = dataset.taxa_blocks[0]
            need_to_add_taxa = False
        if taxa_block is None:
            taxa_block = taxa.TaxaBlock()
        trees_block = self.read_trees(file_obj, taxa_block=taxa_block)
        if need_to_add_taxa:
            dataset.add_taxa_block(taxa_block=taxa_block)
        dataset.add_trees_block(trees_block=trees_block, taxa_block=taxa_block)
        return dataset

    def read_trees(self, file_obj=None, taxa_block=None):
        """
        Instantiates and returns a TreesBlock object based
        on the Newick-formatted contents read from the file
        descriptor object `file_obj`.
        """
        trees_block = trees.TreesBlock()                    
        if taxa_block is not None:
            trees_block.taxa_block = taxa_block
        stream_tokenizer = NexusStreamTokenizer(file_obj)
        tree = parse_newick_tree_stream(stream_tokenizer, taxa_block=taxa_block)
        if taxa_block is None:
            taxa_block = tree.taxa_block
            trees_block.taxa_block = taxa_block
        while tree is not None:
            trees_block.append(tree)
            tree = parse_newick_tree_stream(stream_tokenizer, taxa_block=taxa_block)
        return trees_block

############################################################################
## CLASS: NewickWriter

class NewickWriter(datasets.Writer):
    """
    Handles representation and serialization of a DendroPy Tree object
    in NEWICK format.
    """

    def __init__(self, **kwargs):
        """
        Instantiates the object, setting default for various
        formatting/representation options.
        """
        self.edge_lengths = True
        self.internal_labels = True
        self.support_as_edge_lengths = False
        self.support_as_labels = False
        self.support_as_percentages = False
        self.support_decimals = None

    def write_dataset(self, dataset, dest):
        """
        Writes a DataSet object to a full document-level
        representation of the format being implemented by the
        deriving class. 
        """
        for trees_block in dataset.trees_blocks:
            for tree in trees_block:
                dest.write(self.compose_node(tree.seed_node) + ';\n')                                
                
    def compose_taxlabel(self, label):
        if re.search('[' + NexusStreamTokenizer.whitespace + NexusStreamTokenizer.punctuation + ']', label) != None:
            return "'" + label + "'"
        else:
            return label    
    
    def compose_tree(self, tree):
        "Convienience method.        "
        return self.compose_node(tree.seed_node)

    def choose_display_tag(self, node):
        """
        Based on current settings, the attributes of a node, and
        whether or not the node is a leaf, returns an appropriate tag.
        """
        if hasattr(node, 'taxon') and node.taxon:
            return self.compose_taxlabel(node.taxon.label)
        elif hasattr(node, 'label') and node.label:
            return self.compose_taxlabel(node.label)
        elif len(node.child_nodes()) == 0:
            # force label if a leaf node
            return self.compose_taxlabel(node.oid)
        else:
            return ""
        
    def compose_node(self, node):
        """
        Given a DendroPy Node, this returns the Node as a NEWICK
        statement according to the class-defined formatting rules.
        """
        child_nodes = node.child_nodes()
        if child_nodes:
            subnodes = [self.compose_node(child) for child in child_nodes]
            statement = '(' + ','.join(subnodes) + ')'
            if self.internal_labels:
                statement = statement + self.choose_display_tag(node)
            if node.edge and node.edge.length != None and self.edge_lengths:
                try:
                    statement =  "%s:%f" \
                                % (statement, float(node.edge.length))
                except ValueError:
                    statement =  "%s:%s" \
                                % (statement, node.edge.length)
            return statement
        else:
            if self.internal_labels:
                statement = self.choose_display_tag(node)
            if node.edge and node.edge.length != None and self.edge_lengths:
                try:
                    statement =  "%s:%0.10f" \
                                % (statement, float(node.edge.length))
                except ValueError:
                    statement =  "%s:%s" \
                                % (statement, node.edge.length)
            return statement
            
