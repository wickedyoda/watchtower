package notifications

import (
	"net/url"
	"strings"

	shoutrrrDisco "github.com/containrrr/shoutrrr/pkg/services/discord"
	t "github.com/containrrr/watchtower/pkg/types"
	log "github.com/sirupsen/logrus"
	"github.com/spf13/cobra"
)

const (
	discordType = "discord"
)

type discordTypeNotifier struct {
	webHookURL string
	username   string
	avatarURL  string
}

func newDiscordNotifier(cmd *cobra.Command) t.ConvertibleNotifier {
	flags := cmd.Flags()

	webHookURL, _ := flags.GetString("notification-discord-hook-url")
	if len(webHookURL) <= 0 {
		log.Fatal("Required argument --notification-discord-hook-url(cli) or WATCHTOWER_NOTIFICATION_DISCORD_HOOK_URL(env) is empty.")
	}

	username, _ := flags.GetString("notification-discord-identifier")
	avatarURL, _ := flags.GetString("notification-discord-avatar-url")

	return &discordTypeNotifier{
		webHookURL: webHookURL,
		username:   username,
		avatarURL:  avatarURL,
	}
}

func (n *discordTypeNotifier) GetURL(c *cobra.Command) (string, error) {
	webhookURL, err := url.Parse(n.webHookURL)
	if err != nil {
		return "", err
	}

	pathParts := strings.Split(strings.Trim(webhookURL.Path, "/"), "/")
	webhooksIndex := -1
	for i, part := range pathParts {
		if part == "webhooks" {
			webhooksIndex = i
			break
		}
	}

	if webhooksIndex == -1 || len(pathParts) <= webhooksIndex+2 {
		log.Fatal("Discord webhook URL must contain /webhooks/{id}/{token}")
	}

	config := &shoutrrrDisco.Config{
		WebhookID:  pathParts[webhooksIndex+1],
		Token:      pathParts[webhooksIndex+2],
		Color:      ColorInt,
		SplitLines: true,
	}

	if n.username != "" {
		config.Username = n.username
	}
	if n.avatarURL != "" {
		config.Avatar = n.avatarURL
	}

	return config.GetURL().String(), nil
}
