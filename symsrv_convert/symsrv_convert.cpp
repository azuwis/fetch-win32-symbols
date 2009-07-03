#include <iostream>
#include <string>
#include <vector>

#include "ms_symbol_server_converter.h"

using std::cout;
using std::endl;
using std::string;
using std::vector;
using google_breakpad::MissingSymbolInfo;
using google_breakpad::MSSymbolServerConverter;

int main(int argc, char *argv[])
{
  if (argc < 5) {
    cout << "Usage: " << argv[0]
         << " <symbol server> <symbol path> <debug file> <debug identifier>"
         << endl;
    return 1;
  }

  MissingSymbolInfo missing_info;
  missing_info.debug_file = argv[3];
  missing_info.debug_identifier = argv[4];

  MSSymbolServerConverter converter(argv[2], vector<string>(1, argv[1]));
  string converted_file;

  cout << argv[3] << ": ";
  switch(converter.LocateAndConvertSymbolFile(missing_info,
                                              false,
                                              &converted_file,
                                              NULL)) {
  case MSSymbolServerConverter::LOCATE_SUCCESS:
    cout << " converted: " << converted_file << endl;
    return 0;

  case MSSymbolServerConverter::LOCATE_RETRY:
    cout << " try again later" << endl;
    return 1;

  case MSSymbolServerConverter::LOCATE_FAILURE:
  case MSSymbolServerConverter::LOCATE_NOT_FOUND:
    cout << " failed to locate symbols" << endl;
    return 2;
  }

  // ???
  return 3;
}
