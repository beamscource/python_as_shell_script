# Author Eugen Klein August 2020

import argparse
import subprocess
import os
import xml.etree.ElementTree as ET
import re

def generate_sentence_list(xml_file, number_test_statements):
    
    _, file = os.path.split(xml_file)

    # generate test statements with the source grammar
    print('INFO: Generating {} test statements from {}...'\
        .format(number_test_statements, file))

    try:
        process = subprocess.run(['xmlgenerator', xml_file, '-g_s', '-m_g', \
            number_test_statements], timeout=30, stdout=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        print('ERROR: xmlgenerator exited with status {} during sentence generation: {}'\
            .format(e.returncode, e.output))
        if re.search('(.*?)INVALID_LANGUAGE(.*?)', e.output.decode('utf-8')):
            print('INFO: Please make sure you have the required language installed!')
        elif re.search('(.*?)uri(.*?)file(.*?)not(.*?)found', e.output.decode('utf-8')):
            print('INFO: External grammar not found!')
        elif len(e.output.decode('utf-8')) < 5:
            print('INFO: Please check your xmlgenerator installation!')
        quit()

    except subprocess.TimeoutExpired as e:
        print('ERROR: xmlgenerator timed out during sentence generation.\n' + \
            'The tested grammar might be blocked by forbidden=1. \n {}'.format(e.output))
        quit()

    # UTF-8 decoding and spliting in lines/list elements
    generator_output = process.stdout.decode('utf-8').splitlines()
    # TO DO: test whether generator output is empty
    sentence_list = clean_recog_output(generator_output)

    return sentence_list

def clean_recog_output(generator_output):

    ''' Get rid of generator internal infos printed at the top of the
    generated sentence list.'''

    exclude_list = [':', '|', '==']

    for element in exclude_list:
        generator_output = [line for line in generator_output \
        if (element not in line)]

    return generator_output

def gen_test_file(xml_file, sentence_list):

    ''' Function to test statements and to generate a test set file
    based on the returned slots. '''

    # write a file with test statements for xmlgenerator
    test_file = xml_file.split('.xml')[0] + '.utt'
    f = open(test_file, 'w', encoding='utf-8')
    
    _, gr_file = os.path.split(xml_file)

    # to avoid an empty line at the end of the file
    for line in sentence_list[:-1]:
        f.writelines("{}\n".format(line))
    f.writelines("{}".format(sentence_list[-1]))
    f.close()

    print('INFO: Testing {} to extract slots...'\
        .format(gr_file))

    try:
        process = subprocess.run(['xmlgenerator', xml_file, '-t_f', \
            test_file], stdout=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        print('ERROR: xmlgenerator exited with status {} during sentence testing: {}'\
            .format(e.returncode, e.output))
        quit()

    # decode here as UTF-8
    generator_output = process.stdout.decode('utf-8').splitlines()
    statement_parses = clean_recog_output(generator_output)
    statement_parses = ''.join(statement_parses)

    # delete empty space between tags
    statement_parses = re.sub('>( +?)<', '><', statement_parses)
    statement_parses = ''.join(statement_parses)

    # split output into results for single statements
    statement_parses = [x.group() for x in \
        re.finditer('<\?xml version(.*?)</result>', statement_parses)]

    #_, grammar_name = os.path.split(xml_file)
    grammar_name = xml_file

    # parse XML elements and get a slot dict for every parse
    test_case_list = get_slot_values(grammar_name, statement_parses)

    return statement_parses, test_case_list 

def get_slot_values(grammar_name, statement_parses):

    # variable for slot dictionaries
    test_case_list = []

    # extract meaning slots and literals for every parse
    for i, parse in enumerate(statement_parses):

        root = ET.fromstring(statement_parses[i])

        # create slot dictionary for each parse
        test_case = {'grammar_name' : grammar_name}

        # slots:
        for element in root.iter('instance'):
            for slot in element:
                if slot.tag != 'grammar_id':
                    if isinstance(slot.text, str):
                        test_case[slot.tag] = slot.text.strip()
                    elif slot.text is 'None' or slot.text is None:
                        test_case[slot.tag] = ""

        test_case_list.append(test_case)

    return test_case_list

def compare_test_sets(test_set_file_source, test_set_file_compare, source_grammar):

    _, file = os.path.split(source_grammar)
    comparison_file = source_grammar.split('.xml')[0] + '.comp'
    _, comp_file = os.path.split(comparison_file)
    key_mismatches = 0
    slot_mismatches = 0

    f = open(comparison_file, 'w', encoding='utf-8')

    for s_test_case, c_test_case in zip(test_set_file_source, \
        test_set_file_compare):

        line_start = s_test_case['grammar_name'] + ' "{}"'.format(s_test_case['literal_value'])

        for (key_s, value_s), (key_c, value_c) in zip(s_test_case.items(), \
            c_test_case.items()):
            # skip following slots
            if key_s not in {'literal_value', 'grammar_name', 'grammar_version'}:
                if key_s == key_c:
                    if value_s == value_c:
                        f.writelines(line_start + ' ' + key_s + ' "{}"\n'.format(value_s))
                    else:
                        f.writelines(line_start + ' ' + key_s + ' "{}#{}"\n'.format(value_s, value_c))
                        key_mismatches += 1
                else:
                    f.writelines(line_start + ' ' + key_s + ' "{}"\n'.format('KEY_MISMATCH {}'.format(key_c)))
                    slot_mismatches += 1

    f.close()

    if slot_mismatches or key_mismatches:
        print('INFO: ERROR!!! MISMATCHES FOUND!!!')
    print('INFO: There were {} slot (key) and {} value mismatches during comparison.'\
        .format(slot_mismatches, key_mismatches, file))
    print('INFO: See {} for details.'\
        .format(comp_file))

def write_tset_file(test_case_list, xml_file, mode):

    # write an test set file 
    test_set_file = xml_file.split('.xml')[0] + '.tset'
    _, file = os.path.split(test_set_file)
    
    f = open(test_set_file, mode, encoding='utf-8')

    # format for each line:
    # grammar_name "test_sentence" variable variable_value
    for case in test_case_list:
        
        line_start = case['grammar_name'] + ' "{}"'.format(case['literal_value'])
        
        for key in case:
            # skip following slots
            if key not in {'literal_value', 'grammar_name', 'grammar_version'}:
                f.writelines(line_start + ' ' + key + ' "{}"\n'.format(case[key]))

    f.close()

    print('INFO: A test set was added to {}.'.format(file))

def set_environment(environment):

    print('INFO: Setting environment to {}.'.format(environment))
    try:
        process = subprocess.run(['C:\\bash.exe', \
            environment], check=True)
    except subprocess.CalledProcessError as e:
        print('ERROR: Trying to set evironment exited with status {}, returning {}'\
            .format(e.returncode, e.output))
        quit()

def main(args):

    ''' If source_location is a file with a grammar, generate a statement
        list from it and test the grammar to extract corresponding slot
        values. If source_location is a directory, run a for loop
        iterating over all xml files generating statements for each.

        When a second grammar is provided, it is used to test identical
        statements generated from the first grammar. Results of both grammars
        are then compared on-the-fly and the result of this comparison is
        written to a .comp file.

        With option -tset it possible to generate a .tset file per grammar
        instead of an on-the-fly comparison.'''

    # setting the generator enviroments for the comparison
    source_environment = 'C:\\{}\\env.sh'\
        .format(args.source_environment)
    update_environment = 'C:\\{}env.sh'\
        .format(args.update_environment)

    source_location = args.source
    compare_subfolder_suffix = args.update
    number_test_statements = args.max_gen
    tset = args.tset_file
    delete = args.delete_files

    if os.path.isfile(source_location):
        
        source_grammar = source_location
        path, grammar_name = os.path.split(source_location)
        compare_grammar = os.path.join(path, compare_subfolder_suffix, \
                grammar_name)

        if os.path.isfile(compare_grammar) or tset:

            print('\n====================================================================')
            set_environment(source_environment)
            sentence_list = generate_sentence_list(source_grammar, \
                number_test_statements)
            statement_parses_source, test_set_file_source = gen_test_file(source_grammar, \
                sentence_list)

            if tset:
                write_tset_file(test_set_file_source, source_grammar, 'w')

                # add same test set for updated grammar if this
                # grammar exists in a subfolder
                if os.path.isfile(compare_grammar):
                    test_case_list_compare = get_slot_values(compare_grammar, \
                        statement_parses_source)
                    write_tset_file(test_case_list_compare, source_grammar, 'a+')
            else:
                print('INFO: Starting comparison to the second grammar.')
                # change xmlgenerator environment
                set_environment(update_environment)
                _, test_set_file_compare = gen_test_file(compare_grammar, \
                    sentence_list)
                compare_test_sets(test_set_file_source, test_set_file_compare, \
                    source_grammar)
        else:
            print('INFO: Provide a second grammar at {} for comparison or generate a tset file.'\
                .format(compare_grammar))
            quit()

        print('\nGrammar file processed.')
        print('====================================================================')

    elif os.path.isdir(source_location):
        
        grammar_list = []
        # search only for xml files
        for file in os.listdir(source_location):
            if file.endswith('.xml'):
                grammar_list.append(file)

        for grammar in grammar_list:

            source_grammar = os.path.join(source_location, grammar)
            compare_grammar = os.path.join(source_location, compare_subfolder_suffix, \
                grammar)

            if os.path.isfile(compare_grammar) or tset:

                print('\n====================================================================')
                set_environment(source_environment)
                sentence_list = generate_sentence_list(source_grammar, \
                    number_test_statements)
                statement_parses_source, test_set_file_source = gen_test_file(source_grammar, \
                    sentence_list)

                if tset:
                    write_tset_file(test_set_file_source, source_grammar, 'w')

                    # add same test set for updated grammar if this
                    # grammar exists in a subfolder
                    if os.path.isfile(compare_grammar):
                        test_case_list_compare = get_slot_values(compare_grammar, \
                            statement_parses_source)
                        write_tset_file(test_case_list_compare, source_grammar, 'a+')
                else:
                    print('INFO: Starting comparison to the second grammar.')
                    # change xmlgenerator environment
                    set_environment(update_environment)
                    _, test_set_file_compare = gen_test_file(compare_grammar, \
                        sentence_list)
                    compare_test_sets(test_set_file_source, test_set_file_compare, \
                    source_grammar)
            else:
                print('\n====================================================================')
                print('INFO: Provide a second grammar at {} for comparison or generate a tset file.'\
                    .format(compare_grammar))
                continue

        # delete statement files
        if delete:
            to_delete_list = []
            for file in os.listdir(source_location):
                if file.endswith('.utt'):
                    to_delete_list.append(file)
            
            for file in to_delete_list:
                os.remove(os.path.join(source_location, file))

                if os.path.isfile(os.path.join(source_location, compare_subfolder_suffix, \
                    file)):
                    os.remove(os.path.join(source_location, compare_subfolder_suffix, \
                        file))

        print('\nAll grammar files in {} processed.'.format(source_location))
        print('====================================================================')

    else:
        print('Given directory not found. Check for any typos in the path name.')

if __name__ == "__main__":

    ''' Wrapper script using xmlgenerator to generate test statements from a source
    grammar and to test the grammar extracting slot values.
    Combining test statements and corresponding slot values, either an on-the-fly
    comparison to a second grammar is made or a test set file is
    generated. 

    Useful to test grammar B that was updated from grammar A. '''

    parser = argparse.ArgumentParser(description='Perform an on-the-fly comparison of two \
        grammar files or generate a test set file to run regression tests.')

    parser.add_argument('-s', '--source', required=True, help="File or folder \
        containing the scource grammar(s).")
    parser.add_argument('-m_g', '--max_gen', default='100', help="Max number \
        of utt erances to be generated with the source grammar(s).")
    parser.add_argument('-u', '--update', default='updated', help="Subfolder \
        containing the updated grammar(s).")
    parser.add_argument('-s_e', '--source_environment', default='ver_1', \
        help="xmlgenerator version used for source grammar(s).")
    parser.add_argument('-u_e', '--update_environment', default='ver_2', \
        help="xmlgenerator version used for updated grammar(s).")
    parser.add_argument('-tset', '--tset_file', action='store_true', \
        help="Generate a tset file instead of an on-the-fly comparison.")
    parser.add_argument('-delete', '--delete_files', action='store_true', \
        help="Delete statement files.")

    args = parser.parse_args()
    main(args)
