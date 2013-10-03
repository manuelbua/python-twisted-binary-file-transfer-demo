# -*- coding: utf-8 -*-
#
# Name: Pyton Twisted binary file transfer demo (server)
# Description: Simple demo which shows how you can transfer binary files using
# the Twisted framework.
#
# Keep in mind that this is only a demo and there are many possible scenarios
# where program can break.
#
# Author: Tomaž Muraus (http://www.tomaz-muraus.info)
# License: GPL

# Requirements:
# - Python >= 2.5
# - Twisted (http://twistedmatrix.com/)

import os
import optparse

from twisted.internet import reactor, protocol
from twisted.protocols import basic

from common import COMMANDS, display_message, validate_file_md5_hash, \
    get_file_md5_hash, read_bytes_from_file


class FileTransferProtocol(basic.LineReceiver):
    delimiter = '\n'

    def connectionMade(self):
        self.factory.clients.append(self)
        self.file_handler = None
        self.file_data = ()

        self._send_txt('Welcome!\n'
            'Type help for list of all the available commands'
        )

        display_message('Connection from: %s (%d clients total)' % (
            self.transport.getPeer().host, len(self.factory.clients)))

    def connectionLost(self, reason):
        self.factory.clients.remove(self)
        self.file_handler = None
        self.file_data = ()

        display_message('Connection from %s lost (%d clients left)' % (
            self.transport.getPeer().host, len(self.factory.clients)))

    def lineReceived(self, line):
        display_message(
            'Received the following line from the client [%s]: %s' % (
                self.transport.getPeer().host, line))

        data = self._cleanAndSplitInput(line)
        if len(data) == 0 or data == '':
            return

        command = data[0].lower()
        if not command in COMMANDS:
            self._send_txt('Invalid command')
            return
        if command == 'list':
            self._send_list_of_files()
        elif command == 'get':
            try:
                filename = data[1]
            except IndexError:
                self._send_txt('Missing filename')
                return

            send_all = filename == 'all'

            if send_all or not self.factory.files:
                self.factory.files = self._get_file_list()

            if not send_all and filename not in self.factory.files:
                self._send_txt(
                    'File with filename %s does not exist' % filename)
                return

            if send_all:
                display_message(
                    'Sending all %d files..' % (len(self.factory.files)))
                self.transport.write("FILES %s\n" % len(self.factory.files))
            else:
                self.transport.write("FILES 1\n")

            def send_single(file_name):
                display_message('Sending file: %s (%d KB, %s)' % (
                    file_name, self.factory.files[file_name][1] / 1024,
                    self.factory.files[file_name][2]))

                # send file's name, size and md5 hash
                self.transport.write(
                    'HASH %s %s %s\n' % (
                        file_name, self.factory.files[file_name][2],
                        self.factory.files[file_name][1]))

                # send binary data
                for bytes_data in read_bytes_from_file(
                        os.path.join(self.factory.files_path, file_name)):
                    self.transport.write(bytes_data)

            if send_all:
                for f in self.factory.files:
                    send_single(f)
            else:
                send_single(filename)

        elif command == 'put':
            try:
                filename = data[1]
                file_hash = data[2]
            except IndexError:
                self._send_txt('Missing filename or file MD5 hash')
                return

            self.file_data = (filename, file_hash)

            # Switch to the raw mode (for receiving binary data)
            print 'Receiving file: %s' % filename
            self.setRawMode()
        elif command == 'help':
            help_text = 'Available commands:\n\n'

            for key, value in COMMANDS.iteritems():
                help_text += '%s - %s\n' % (value[0], value[1])

            self._send_txt(help_text)
        elif command == 'quit':
            self.transport.loseConnection()

    # TODO, fix everything
    def rawDataReceived(self, data):
        filename = self.file_data[0]
        file_path = os.path.join(self.factory.files_path, filename)

        display_message('Receiving file chunk (%d KB)' % (len(data)))

        if not self.file_handler:
            self.file_handler = open(file_path, 'wb')

        if data.endswith('\r\n'):
            # Last chunk
            data = data[:-2]
            self.file_handler.write(data)
            self.setLineMode()

            self.file_handler.close()
            self.file_handler = None

            if validate_file_md5_hash(file_path, self.file_data[1]):
                self._send_txt('File was successfully transfered and saved')

                display_message(
                    'File %s has been successfully transfered' % (filename))
            else:
                os.unlink(file_path)
                self._send_txt(
                    'File was successfully transfered but not saved, '
                    'due to invalid MD5 hash')

                display_message(
                    'File %s has been successfully transfered, '
                    'but deleted due to invalid MD5 hash' % (
                        filename))
        else:
            self.file_handler.write(data)


    def _send_txt(self,data):
        self.transport.write("TXT %d\n" % len(data))
        self.transport.write("%s" % data)

    #def _send_file(self,data):

    def _send_list_of_files(self):
        files = self._get_file_list()
        self.factory.files = files

        files_list = 'Files (%d): \n\n' % len(files)
        for key, value in files.iteritems():
            files_list += '- %s (%d.2 KB)\n' % (key, (value[1] / 1024.0))

        self._send_txt(files_list)

    def _get_file_list(self):
        """ Returns a list of the files in the specified directory as a
        dictionary:

        dict['file name'] = (file path, file size, file md5 hash)
        """

        file_list = {}
        for filename in os.listdir(self.factory.files_path):
            file_path = os.path.join(self.factory.files_path, filename)

            if os.path.isdir(file_path):
                continue

            file_size = os.path.getsize(file_path)
            try:
                md5_hash = get_file_md5_hash(file_path)
            except IOError:
                print "Couldn't read", file_path
            else:
                file_list[filename] = (file_path, file_size, md5_hash)

        return file_list

    def _cleanAndSplitInput(self, input):
        input = input.strip()
        input = input.split(' ')

        return input


class FileTransferServerFactory(protocol.ServerFactory):
    protocol = FileTransferProtocol

    def __init__(self, files_path):
        self.files_path = files_path

        self.clients = []
        self.files = None


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('-p', '--port', action='store', type='int', dest='port',
                      default=1234, help='server listening port')
    parser.add_option('--path', action='store', type='string', dest='path',
                      help='directory where the incoming files are saved',
                      default='/tmp/srv')
    (options, args) = parser.parse_args()

    display_message('Listening on port %d, serving files from directory: %s' % (
        options.port, options.path))

    reactor.listenTCP(options.port, FileTransferServerFactory(options.path))
    reactor.run()