#include <stdio.h>
#include <signal.h>
#include <string.h>
#include <fcntl.h>

#include <sys/time.h>
#include <sys/socket.h>

#include <netinet/in.h>

#include <linux/kd.h>

#define CLK_FREQ 1193180

int term;

enum cmd_t {CMD_KA, CMD_PING, CMD_QUIT, CMD_PLAY};

struct cmd_buffer {
	int cmd;
	int data[8];
};

void sigalrm(int sig) {
	ioctl(term, KIOCSOUND, 0);
}

int main(int argc, char **argv) {
	struct sockaddr_in addr, remote;
	int sock, rlen = sizeof(remote), i;
	struct itimerval tmr;
	struct cmd_buffer cmd;
	struct sigaction sa;

	if((term = open("/dev/console", O_WRONLY)) < 0) {
		perror("open");
		return 1;
	}
	if((sock = socket(AF_INET, SOCK_DGRAM, 0)) < 0) {
		perror("socket");
		return 1;
	}

	memset(&addr, 0, sizeof(addr));
	addr.sin_family = AF_INET;
	addr.sin_addr.s_addr = htonl(INADDR_ANY);
	addr.sin_port = htons(13676);
	if((bind(sock, (struct sockaddr *) &addr, sizeof(addr))) < 0) {
		perror("bind");
		return 1;
	}

	sa.sa_handler = sigalrm;
	sa.sa_flags = SA_NODEFER | SA_RESTART;
	sigemptyset(&sa.sa_mask);
	sigaction(SIGALRM, &sa, NULL);

	printf("Ready to begin (listening on 13676)\n");
	memset(&tmr, 0, sizeof(tmr));
	while(1) {
		if(recvfrom(sock, &cmd, sizeof(cmd), 0, (struct sockaddr *) &remote, &rlen) < 0) {
			perror("recvfrom");
			return 1;
		}
		cmd.cmd = ntohl(cmd.cmd);
		for(i = 0; i < 8; i++) cmd.data[i] = ntohl(cmd.data[i]);
		/* printf("From %s:%d, cmd %d\n", inet_ntoa(remote.sin_addr.s_addr), remote.sin_port, cmd.cmd); */
		switch((enum cmd_t) cmd.cmd) {
			case CMD_QUIT:
				return 0;
				break;

			case CMD_PING:
				sendto(sock, &cmd, sizeof(cmd), 0, (struct sockaddr *) &remote, rlen);
				break;

			case CMD_PLAY:
				tmr.it_value.tv_sec = cmd.data[0];
				tmr.it_value.tv_usec = cmd.data[1];
				setitimer(ITIMER_REAL, &tmr, NULL);
				ioctl(term, KIOCSOUND, (int) (CLK_FREQ / cmd.data[2]));
		
			default:
				printf("WARNING: Unknown cmd %d\n", cmd.cmd);
			case CMD_KA: 
				break;
		}
	}
}
