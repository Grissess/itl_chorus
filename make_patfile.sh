# Convert the FreePats Drums_000 directory to ITL Chorus drums.tar.bz2
# Note: technically, this must be run in a directory with subdirectories
# starting with a MIDI pitch, and containing a text file with a
# "convert_to_wav:" command that produces a .wav in that working directory.
# sox is required to convert the audio. This handles the dirt-old options
# for sox in the text files explicitly to support the FreePats standard.
# The current version was checked in from the Drums_000 directory to be
# found in the TAR at this URL:
# http://freepats.zenvoid.org/samples/freepats/freepats-raw-samples.tar.bz2
# Thank you again, FreePats!

rm *.wav .wav *.raw .raw

for i in *; do
	if [ -d $i ]; then
		pushd $i
		eval `grep 'convert_to_wav' *.txt | sed -e 's/convert_to_wav: //' -e 's/-w/-b 16/' -e 's/-s/-e signed/' -e 's/-u/-e unsigned/'`
		PITCH=`echo "$i" | sed -e 's/^\([0-9]\+\).*$/\1/g'`
		# From broadcast.py, eval'd in Python for consistent results
		FRQ=`echo $PITCH | python2 -c "print(int(440.0 * 2**((int(raw_input())-69)/12.0)))"`
		echo "WRITING $FRQ.wav"
		[ -z "$FRQ" ] && echo "!!! EMPTY FILENAME?"
		sox *.wav -r 44100 -c 1 -e signed -b 32 -t raw ../$FRQ.raw
		popd
	fi
done

rm drums.tar.bz2
tar cjf drums.tar.bz2 *.raw
