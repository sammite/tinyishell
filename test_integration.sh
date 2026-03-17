#!/bin/bash

# 1. Build the project
# We'll use a test secret key
SECRET="testkey"
echo "Building tsh and tshd..."
make clean > /dev/null
make linux SECRET_KEY=$SECRET > /dev/null

# 2. Execute tshd
echo "Starting tshd..."
./tshd

# Give it a moment to start and fork
sleep 1

# 3. Execute client in ls mode
echo "--- Listing / ---"
./tsh -s $SECRET localhost ls /

echo -e "\n--- Listing /home ---"
./tsh -s $SECRET localhost ls /home

# 4. Test File Operations (put/get)
echo -e "\n--- Testing File Operations ---"
echo "test" > tmpfile
echo "Putting 'tmpfile' to '/var/tmp'..."
./tsh -s $SECRET localhost put tmpfile /var/tmp

# Verification: Get it back to a different local file
echo "Getting '/var/tmp/tmpfile' back as 'tmpfile_returned'..."
# Note: tsh put/get takes <remote-dir> or <local-dir> as second argument
./tsh -s $SECRET localhost get /var/tmp/tmpfile .
mv tmpfile tmpfile_returned # Ensure we compare against original
echo "test" > tmpfile # Re-create original for comparison

if diff tmpfile tmpfile_returned > /dev/null; then
    echo "SUCCESS: File put and get match!"
else
    echo "FAILURE: File put and get do not match!"
    diff tmpfile tmpfile_returned
fi

# 5. Test Exec Operation
echo -e "\n--- Testing Exec Operation ---"
# Use exec to touch a new file
echo "Exec'ing '/usr/bin/touch /var/tmp/touched_file'..."
./tsh -s $SECRET localhost exec "/usr/bin/touch /var/tmp/touched_file"

# Verification: LS the directory and grep for the touched file
echo "Verifying via ls /var/tmp..."
if ./tsh -s $SECRET localhost ls /var/tmp | grep "touched_file" > /dev/null; then
    echo "SUCCESS: '/var/tmp/touched_file' exists!"
else
    echo "FAILURE: '/var/tmp/touched_file' not found!"
fi

# 6. Clean up
echo -e "\nCleaning up..."
# Use ps to find the PID of the tshd process
TSHD_PID=$(ps -ef | grep '[t]shd' | awk '{print $2}')

if [ -z "$TSHD_PID" ]; then
    echo "tshd process not found."
else
    echo "Killing tshd (PID: $TSHD_PID)"
    kill $TSHD_PID
fi

# Remove temporary test files
rm -f tmpfile tmpfile_returned /var/tmp/tmpfile /var/tmp/touched_file
make clean > /dev/null
echo "Test script finished."
