import random
import subprocess
import os
import discord
from discord.ext import commands, tasks
import asyncio
from discord import app_commands
import psutil
from datetime import datetime

# Configuration
TOKEN = ''  # TOKEN HERE
RAM_LIMIT = '2g'
SERVER_LIMIT = 12
DEPLOY_CHANNEL_ID = 123456789  # CHANGE TO YOUR DEPLOY CHANNEL ID
LOGS_CHANNEL_ID = 123456789    # CHANGE TO YOUR LOGS CHANNEL ID
ADMIN_IDS = [1234567890]       # ADD YOUR ADMIN USER IDs HERE

database_file = 'database.txt'

intents = discord.Intents.default()
intents.messages = False
intents.message_content = False

bot = commands.Bot(command_prefix='/', intents=intents)

# Embed color constant
EMBED_COLOR = 0x9B59B6  # Purple color

# OS Options with fancy emojis
OS_OPTIONS = {
    "ubuntu": {"image": "ubuntu-vps", "name": "Ubuntu 22.04", "emoji": "🐧"},
    "debian": {"image": "debian-vps", "name": "Debian 12", "emoji": "🦕"},
    "alpine": {"image": "alpine-vps", "name": "Alpine Linux", "emoji": "⛰️"},
    "arch": {"image": "arch-vps", "name": "Arch Linux", "emoji": "🎯"},
    "kali": {"image": "kali-vps", "name": "Kali Linux", "emoji": "💣"},
    "fedora": {"image": "fedora-vps", "name": "Fedora", "emoji": "🎩"}
}

def generate_random_port():
    return random.randint(1025, 65535)

def add_to_database(user, container_name, ssh_command):
    with open(database_file, 'a') as f:
        f.write(f"{user}|{container_name}|{ssh_command}\n")

def remove_from_database(ssh_command):
    if not os.path.exists(database_file):
        return
    with open(database_file, 'r') as f:
        lines = f.readlines()
    with open(database_file, 'w') as f:
        for line in lines:
            if ssh_command not in line:
                f.write(line)

def clear_database():
    if os.path.exists(database_file):
        os.remove(database_file)

async def capture_ssh_session_line(process):
    while True:
        output = await process.stdout.readline()
        if not output:
            break
        output = output.decode('utf-8').strip()
        if "ssh session:" in output:
            return output.split("ssh session:")[1].strip()
    return None

def get_user_servers(user):
    if not os.path.exists(database_file):
        return []
    servers = []
    with open(database_file, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 3 and parts[0] == user:
                servers.append(line.strip())
    return servers

def count_user_servers(user):
    return len(get_user_servers(user))

def get_container_id_from_database(user, container_name):
    if not os.path.exists(database_file):
        return None
    with open(database_file, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 3 and parts[0] == user and container_name in parts[1]:
                return parts[1]
    return None

def get_system_resources():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        mem_total = mem.total / (1024 ** 3)
        mem_used = mem.used / (1024 ** 3)
        disk = psutil.disk_usage('/')
        disk_total = disk.total / (1024 ** 3)
        disk_used = disk.used / (1024 ** 3)
        
        return {
            'cpu': cpu_percent,
            'memory': {'total': round(mem_total, 2), 'used': round(mem_used, 2), 'percent': mem.percent},
            'disk': {'total': round(disk_total, 2), 'used': round(disk_used, 2), 'percent': disk.percent}
        }
    except Exception:
        return {
            'cpu': 0,
            'memory': {'total': 0, 'used': 0, 'percent': 0},
            'disk': {'total': 0, 'used': 0, 'percent': 0}
        }

@bot.event
async def on_ready():
    change_status.start()
    print(f'✨ Bot is ready. Logged in as {bot.user} ✨')
    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"Error syncing commands: {e}")

@tasks.loop(seconds=5)
async def change_status():
    try:
        instance_count = len(open(database_file).readlines()) if os.path.exists(database_file) else 0
        statuses = [  
            f"🌠 Managing {instance_count} Cloud Instances",  
            f"⚡ Powering {instance_count} Servers",  
            f"🔮 Watching over {instance_count} VMs",
            f"🚀 Hosting {instance_count} Dreams"
        ]  
        await bot.change_presence(activity=discord.Game(name=random.choice(statuses)))  
    except Exception as e:  
        print(f"💥 Failed to update status: {e}")

async def send_to_logs(message):
    try:
        channel = bot.get_channel(LOGS_CHANNEL_ID)
        if channel:
            perms = channel.permissions_for(channel.guild.me)
            if perms.send_messages:
                timestamp = datetime.now().strftime("%H:%M:%S")
                await channel.send(f"`[{timestamp}]` {message}")
    except Exception as e:
        print(f"Failed to send logs: {e}")

class OSSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=f"{os_data['emoji']} {os_data['name']}", value=os_id)
            for os_id, os_data in OS_OPTIONS.items()
        ]
        super().__init__(
            placeholder="✨ Select your OS...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(thinking=True)
            os_id = self.values[0]
            os_data = OS_OPTIONS[os_id]
            await create_server(interaction, os_data["image"], os_data["name"], os_data["emoji"])
        except Exception as e:
            print(f"Error in OSSelect callback: {e}")
            try:
                await interaction.followup.send("❌ An error occurred while processing your request.", ephemeral=True)
            except:
                pass

class OSView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(OSSelect())

@bot.tree.command(name="deploy", description="🚀 Create a new cloud instance")
async def deploy(interaction: discord.Interaction):
    try:
        if interaction.channel_id != DEPLOY_CHANNEL_ID:
            embed = discord.Embed(
                title="🚫 Wrong Channel",
                description=f"Please use this command in the <#{DEPLOY_CHANNEL_ID}> channel.",
                color=EMBED_COLOR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🚀 Cloud Instance Deployment",
            description="✨ Select your preferred OS from the menu below:",
            color=EMBED_COLOR
        )
        embed.set_footer(text="Each user can create up to 12 instances")
        await interaction.response.send_message(embed=embed, view=OSView())
    except Exception as e:
        print(f"Error in deploy command: {e}")
        try:
            await interaction.response.send_message("❌ An error occurred while processing your request.", ephemeral=True)
        except:
            pass

async def create_server(interaction, image, os_name, os_emoji):
    try:
        user = str(interaction.user)
        
        if count_user_servers(user) >= SERVER_LIMIT:  
            embed = discord.Embed(  
                title="🚫 Limit Reached",  
                description=f"❌ You've reached your limit of {SERVER_LIMIT} instances!",
                color=EMBED_COLOR  
            )  
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                try:
                    await interaction.channel.send(embed=embed)
                except:
                    pass
            return

        embed = discord.Embed(
            title=f"⚙️ {os_emoji} Creating {os_name} Instance",
            description=f"```🔮 Preparing your magical {os_name} experience...```",
            color=EMBED_COLOR
        )
        embed.set_footer(text="This may take a moment...")
        
        try:
            msg = await interaction.followup.send(embed=embed, wait=True)
        except:
            try:
                msg = await interaction.channel.send(embed=embed)
            except Exception as e:
                print(f"Failed to send message: {e}")
                return

        try:  
            container_id = subprocess.check_output(["docker", "run", "-itd", "--privileged", image]).strip().decode('utf-8')  
            await send_to_logs(f"🔧 {interaction.user.mention} just deployed {os_emoji} {os_name} (ID: `{container_id[:12]}`)")
        except subprocess.CalledProcessError as e:  
            embed = discord.Embed(  
                title="❌ Creation Failed",  
                description=f"```🛠️ Error creating container:\n{e}```",  
                color=EMBED_COLOR  
            )  
            try:
                await msg.edit(embed=embed)
            except:
                pass
            return  

        try:  
            exec_cmd = await asyncio.create_subprocess_exec("docker", "exec", container_id, "tmate", "-F",  
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  
            ssh_session_line = await capture_ssh_session_line(exec_cmd)  
            
            if ssh_session_line:  
                dm_embed = discord.Embed(  
                    title=f"🎉 {os_emoji} {os_name} Instance Ready!",  
                    description=f"**🔑 SSH Command:**\n```{ssh_session_line}```",  
                    color=EMBED_COLOR  
                )  
                dm_embed.add_field(name="🖥️ OS", value=os_name, inline=True)  
                dm_embed.add_field(name="🧠 RAM", value="2GB", inline=True)  
                dm_embed.add_field(name="⚡ CPU", value="2 Cores", inline=True)  
                dm_embed.set_footer(text="💎 This instance will auto-delete after 4 hours of inactivity")  
                
                response_embed = discord.Embed(  
                    title="✅ Deployment Successful!",  
                    description=f"**{os_emoji} {os_name}** instance created!\n📩 Check your DMs for connection details.",
                    color=EMBED_COLOR  
                )  
                
                try:
                    await interaction.user.send(embed=dm_embed)
                except:
                    response_embed.description = f"**{os_emoji} {os_name}** instance created!\n⚠️ Could not send DM - check your privacy settings."
                
                add_to_database(user, container_id, ssh_session_line)  
                try:
                    await msg.edit(embed=response_embed)  
                except:
                    pass
            else:  
                embed = discord.Embed(  
                    title="⚠️ Timeout",  
                    description="```⏳ Instance is taking longer than expected...```",  
                    color=EMBED_COLOR  
                )  
                try:
                    await msg.edit(embed=embed)  
                except:
                    pass
                subprocess.run(["docker", "kill", container_id], stderr=subprocess.DEVNULL)  
                subprocess.run(["docker", "rm", container_id], stderr=subprocess.DEVNULL)
                
        except Exception as e:  
            embed = discord.Embed(  
                title="❌ SSH Setup Failed",  
                description=f"```💥 Error:\n{e}```",  
                color=EMBED_COLOR  
            )  
            try:
                await msg.edit(embed=embed)  
            except:
                pass
            subprocess.run(["docker", "kill", container_id], stderr=subprocess.DEVNULL)  
            subprocess.run(["docker", "rm", container_id], stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Error in create_server: {e}")

@bot.tree.command(name="start", description="🟢 Start your instance")
@app_commands.describe(container_id="Your instance ID")
async def start_server(interaction: discord.Interaction, container_id: str):
    try:
        user = str(interaction.user)
        container_info = None
        ssh_command = None
        
        if not os.path.exists(database_file):
            embed = discord.Embed(  
                title="🚫 No Instances Found",  
                description="You don't have any instances!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return

        # Search database for this user's container
        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 3 and user == parts[0] and container_id in parts[1]:
                    container_info = parts[1]
                    ssh_command = parts[2]
                    break

        if not container_info:  
            embed = discord.Embed(  
                title="🚫 Instance Not Found",  
                description="No instance found with that ID that belongs to you!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return  

        try:  
            # First check if container exists
            check_cmd = subprocess.run(["docker", "inspect", "--format='{{.State.Status}}'", container_info], 
                                     capture_output=True, text=True)
            
            if check_cmd.returncode != 0:
                embed = discord.Embed(  
                    title="❌ Container Not Found",  
                    description=f"Container `{container_info[:12]}` doesn't exist in Docker!",
                    color=EMBED_COLOR  
                )  
                await interaction.response.send_message(embed=embed, ephemeral=True)
                # Remove from database since it doesn't exist
                remove_from_database(ssh_command)
                return
            
            # Start the container
            subprocess.run(["docker", "start", container_info], check=True)
            
            # Get new SSH connection details (since tmate session changes)
            try:
                exec_cmd = await asyncio.create_subprocess_exec(
                    "docker", "exec", container_info, "tmate", "-F",
                    stdout=asyncio.subprocess.PIPE, 
                    stderr=asyncio.subprocess.PIPE
                )  
                ssh_session_line = await capture_ssh_session_line(exec_cmd)
                
                if ssh_session_line:
                    # Update database with new SSH command
                    remove_from_database(ssh_command)
                    add_to_database(user, container_info, ssh_session_line)
                    
                    # Send DM with new connection details
                    try:
                        dm_embed = discord.Embed(  
                            title="🟢 Instance Started",  
                            description=f"**🔑 New SSH Command:**\n```{ssh_session_line}```",  
                            color=EMBED_COLOR  
                        )
                        await interaction.user.send(embed=dm_embed)
                    except discord.Forbidden:
                        pass  # Can't send DM, we'll include in main response
                    
                    embed = discord.Embed(  
                        title="🟢 Instance Started",  
                        description=f"Instance `{container_info[:12]}` has been started!\n📩 Check your DMs for new connection details.",
                        color=EMBED_COLOR  
                    )  
                else:
                    embed = discord.Embed(  
                        title="🟢 Instance Started",  
                        description=f"Instance `{container_info[:12]}` has been started!\n⚠️ Could not get new SSH details.",
                        color=EMBED_COLOR  
                    )
            except Exception as e:
                print(f"Error getting new SSH session: {e}")
                embed = discord.Embed(  
                    title="🟢 Instance Started",  
                    description=f"Instance `{container_info[:12]}` has been started!\n⚠️ Could not refresh SSH details.",
                    color=EMBED_COLOR  
                )
            
            await interaction.response.send_message(embed=embed)  
            await send_to_logs(f"🟢 {interaction.user.mention} started instance `{container_info[:12]}`")
            
        except subprocess.CalledProcessError as e:  
            embed = discord.Embed(  
                title="❌ Error Starting Instance",  
                description=f"```{e.stderr if e.stderr else e.stdout}```",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"Error in start_server: {e}")
        try:
            await interaction.response.send_message(
                "❌ An error occurred while processing your request.", 
                ephemeral=True
            )
        except:
            pass

@bot.tree.command(name="stop", description="🛑 Stop your instance")
@app_commands.describe(container_id="Your instance ID")
async def stop_server(interaction: discord.Interaction, container_id: str):
    try:
        user = str(interaction.user)
        container_info = None
        
        if not os.path.exists(database_file):
            embed = discord.Embed(  
                title="🚫 No Instances Found",  
                description="You don't have any instances!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return

        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 3 and user == parts[0] and container_id in parts[1]:
                    container_info = parts[1]
                    break

        if not container_info:  
            embed = discord.Embed(  
                title="🚫 Instance Not Found",  
                description="No instance found with that ID that belongs to you!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return  

        try:  
            # First check if container exists
            check_cmd = subprocess.run(["docker", "inspect", container_info], 
                                     capture_output=True, text=True)
            
            if check_cmd.returncode != 0:
                embed = discord.Embed(  
                    title="❌ Container Not Found",  
                    description=f"Container `{container_info[:12]}` doesn't exist in Docker!",
                    color=EMBED_COLOR  
                )  
                await interaction.response.send_message(embed=embed, ephemeral=True)
                # Remove from database since it doesn't exist
                remove_from_database(container_info)
                return
            
            # Stop the container
            subprocess.run(["docker", "stop", container_info], check=True)
            
            embed = discord.Embed(  
                title="🛑 Instance Stopped",  
                description=f"Instance `{container_info[:12]}` has been stopped!",
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed)  
            await send_to_logs(f"🛑 {interaction.user.mention} stopped instance `{container_info[:12]}`")
            
        except subprocess.CalledProcessError as e:  
            embed = discord.Embed(  
                title="❌ Error Stopping Instance",  
                description=f"```{e.stderr if e.stderr else e.stdout}```",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"Error in stop_server: {e}")
        try:
            await interaction.response.send_message(
                "❌ An error occurred while processing your request.", 
                ephemeral=True
            )
        except:
            pass

@bot.tree.command(name="restart", description="🔄 Restart your instance")
@app_commands.describe(container_id="Your instance ID")
async def restart_server(interaction: discord.Interaction, container_id: str):
    try:
        user = str(interaction.user)
        container_info = None
        ssh_command = None
        
        if not os.path.exists(database_file):
            embed = discord.Embed(  
                title="🚫 No Instances Found",  
                description="You don't have any instances!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return

        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 3 and user == parts[0] and container_id in parts[1]:
                    container_info = parts[1]
                    ssh_command = parts[2]
                    break

        if not container_info:  
            embed = discord.Embed(  
                title="🚫 Instance Not Found",  
                description="No instance found with that ID that belongs to you!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return  

        try:  
            # First check if container exists
            check_cmd = subprocess.run(["docker", "inspect", container_info], 
                                     capture_output=True, text=True)
            
            if check_cmd.returncode != 0:
                embed = discord.Embed(  
                    title="❌ Container Not Found",  
                    description=f"Container `{container_info[:12]}` doesn't exist in Docker!",
                    color=EMBED_COLOR  
                )  
                await interaction.response.send_message(embed=embed, ephemeral=True)
                # Remove from database since it doesn't exist
                remove_from_database(ssh_command)
                return
            
            # Restart the container
            subprocess.run(["docker", "restart", container_info], check=True)
            
            # Get new SSH connection details (since tmate session changes)
            try:
                exec_cmd = await asyncio.create_subprocess_exec(
                    "docker", "exec", container_info, "tmate", "-F",
                    stdout=asyncio.subprocess.PIPE, 
                    stderr=asyncio.subprocess.PIPE
                )  
                ssh_session_line = await capture_ssh_session_line(exec_cmd)
                
                if ssh_session_line:
                    # Update database with new SSH command
                    remove_from_database(ssh_command)
                    add_to_database(user, container_info, ssh_session_line)
                    
                    # Send DM with new connection details
                    try:
                        dm_embed = discord.Embed(  
                            title="🔄 Instance Restarted",  
                            description=f"**🔑 New SSH Command:**\n```{ssh_session_line}```",  
                            color=EMBED_COLOR  
                        )
                        await interaction.user.send(embed=dm_embed)
                    except discord.Forbidden:
                        pass  # Can't send DM, we'll include in main response
                    
                    embed = discord.Embed(  
                        title="🔄 Instance Restarted",  
                        description=f"Instance `{container_info[:12]}` has been restarted!\n📩 Check your DMs for new connection details.",
                        color=EMBED_COLOR  
                    )  
                else:
                    embed = discord.Embed(  
                        title="🔄 Instance Restarted",  
                        description=f"Instance `{container_info[:12]}` has been restarted!\n⚠️ Could not get new SSH details.",
                        color=EMBED_COLOR  
                    )
            except Exception as e:
                print(f"Error getting new SSH session: {e}")
                embed = discord.Embed(  
                    title="🔄 Instance Restarted",  
                    description=f"Instance `{container_info[:12]}` has been restarted!\n⚠️ Could not refresh SSH details.",
                    color=EMBED_COLOR  
                )
            
            await interaction.response.send_message(embed=embed)  
            await send_to_logs(f"🔄 {interaction.user.mention} restarted instance `{container_info[:12]}`")
            
        except subprocess.CalledProcessError as e:  
            embed = discord.Embed(  
                title="❌ Error Restarting Instance",  
                description=f"```{e.stderr if e.stderr else e.stdout}```",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"Error in restart_server: {e}")
        try:
            await interaction.response.send_message(
                "❌ An error occurred while processing your request.", 
                ephemeral=True
            )
        except:
            pass

@bot.tree.command(name="remove", description="❌ Remove your instance")
@app_commands.describe(container_id="Your instance ID")
async def remove_server(interaction: discord.Interaction, container_id: str):
    try:
        user = str(interaction.user)
        container_info = None
        ssh_command = None
        
        if not os.path.exists(database_file):
            embed = discord.Embed(  
                title="🚫 No Instances Found",  
                description="You don't have any instances!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return

        with open(database_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 3 and user == parts[0] and container_id in parts[1]:
                    container_info = parts[1]
                    ssh_command = parts[2]
                    break

        if not container_info:  
            embed = discord.Embed(  
                title="🚫 Instance Not Found",  
                description="No instance found with that ID that belongs to you!",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)  
            return  

        try:  
            # First check if container exists
            check_cmd = subprocess.run(["docker", "inspect", container_info], 
                                     capture_output=True, text=True)
            
            if check_cmd.returncode != 0:
                embed = discord.Embed(  
                    title="❌ Container Not Found",  
                    description=f"Container `{container_info[:12]}` doesn't exist in Docker!",
                    color=EMBED_COLOR  
                )  
                await interaction.response.send_message(embed=embed, ephemeral=True)
                # Remove from database since it doesn't exist
                remove_from_database(ssh_command)
                return
            
            # Stop and remove the container
            subprocess.run(["docker", "stop", container_info], check=True)  
            subprocess.run(["docker", "rm", container_info], check=True)  
            
            # Remove from database
            remove_from_database(ssh_command)
            
            embed = discord.Embed(  
                title="🗑️ Instance Removed",  
                description=f"Instance `{container_info[:12]}` has been permanently deleted!",
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed)  
            await send_to_logs(f"❌ {interaction.user.mention} deleted instance `{container_info[:12]}`")
            
        except subprocess.CalledProcessError as e:  
            embed = discord.Embed(  
                title="❌ Error Removing Instance",  
                description=f"```{e.stderr if e.stderr else e.stdout}```",  
                color=EMBED_COLOR  
            )  
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"Error in remove_server: {e}")
        try:
            await interaction.response.send_message(
                "❌ An error occurred while processing your request.", 
                ephemeral=True
            )
        except:
            pass

@bot.tree.command(name="list", description="📜 List your instances")
async def list_servers(interaction: discord.Interaction):
    try:
        user = str(interaction.user)
        servers = get_user_servers(user)
        
        if not servers:
            embed = discord.Embed(
                title="📭 No Instances Found",
                description="You don't have any active instances.",
                color=EMBED_COLOR
            )
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(
            title=f"📋 Your Instances ({len(servers)}/{SERVER_LIMIT})",
            color=EMBED_COLOR
        )
        
        for server in servers:
            parts = server.split('|')
            if len(parts) < 3:
                continue
                
            container_id = parts[1]
            ssh_cmd = parts[2]
            os_type = "Unknown"
            
            for os_id, os_data in OS_OPTIONS.items():
                if os_id in ssh_cmd.lower():
                    os_type = f"{os_data['emoji']} {os_data['name']}"
                    break
                    
            embed.add_field(
                name=f"🖥️ Instance {container_id[:12]}",
                value=f"▫️ OS: {os_type}\n▫️ RAM: 2GB\n▫️ CPU: 2 Cores",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Error in list_servers: {e}")
        try:
            await interaction.response.send_message("❌ An error occurred while processing your request.", ephemeral=True)
        except:
            pass

@bot.tree.command(name="resources", description="📊 Show host system resources")
async def resources_command(interaction: discord.Interaction):
    try:
        resources = get_system_resources()
        
        embed = discord.Embed(
            title="📊 Host System Resources",
            color=EMBED_COLOR
        )
        
        embed.add_field(
            name="💻 CPU Usage",
            value=f"{resources['cpu']}%",
            inline=True
        )
        
        embed.add_field(
            name="🧠 Memory",
            value=f"{resources['memory']['used']}GB / {resources['memory']['total']}GB ({resources['memory']['percent']}%)",
            inline=True
        )
        
        embed.add_field(
            name="💾 Disk Space",
            value=f"{resources['disk']['used']}GB / {resources['disk']['total']}GB ({resources['disk']['percent']}%)",
            inline=True
        )
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Error in resources_command: {e}")
        try:
            await interaction.response.send_message("❌ An error occurred while processing your request.", ephemeral=True)
        except:
            pass

@bot.tree.command(name="help", description="ℹ️ Show help message")
async def help_command(interaction: discord.Interaction):
    try:
        embed = discord.Embed(
            title="✨ Cloud Instance Bot Help",
            description="Here are all available commands:",
            color=EMBED_COLOR
        )

        commands_list = [  
            ("🚀 /deploy", "Create a new cloud instance (OS selection menu)"),  
            ("📜 /list", "List all your instances"),  
            ("🟢 /start <id>", "Start your instance"),  
            ("🛑 /stop <id>", "Stop your instance"),  
            ("🔄 /restart <id>", "Restart your instance"),  
            ("🗑️ /remove <id>", "Delete an instance"),  
            ("📊 /resources", "Show host system resources"),  
            ("🏓 /ping", "Check bot latency"),  
            ("ℹ️ /help", "Show this help message")
        ]  
        
        for cmd, desc in commands_list:  
            embed.add_field(name=cmd, value=desc, inline=False)  
        
        embed.set_footer(text=f"💜 Need help? Contact staff! | Deploy in: <#{DEPLOY_CHANNEL_ID}>")  
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Error in help_command: {e}")
        try:
            await interaction.response.send_message("❌ An error occurred while processing your request.", ephemeral=True)
        except:
            pass

@bot.tree.command(name="ping", description="🏓 Check bot latency")
async def ping_command(interaction: discord.Interaction):
    try:
        latency = round(bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"⚡ Bot latency: {latency}ms",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Error in ping_command: {e}")
        try:
            await interaction.response.send_message("❌ An error occurred while processing your request.", ephemeral=True)
        except:
            pass

bot.run(TOKEN)
