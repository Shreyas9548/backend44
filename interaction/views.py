from django.shortcuts import get_object_or_404
from rest_framework import status, generics
from communication.serializers import MessageSerializer
from rest_framework.decorators import api_view

from rest_framework.response import Response
from rest_framework.views import APIView
from datetime import datetime
from .models import Interaction, Calls, Meetings, Conversation,Email,Group
from tenant.models import Tenant
from django.contrib.contenttypes.models import ContentType
from .serializers import InteractionSerializer, callsSerializer, meetingsSerializer,EmailSerializer,GroupSerializer

from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework import viewsets

from django.http import JsonResponse
# from .utils import fetch_entity_details
from interaction.models import Interaction
from contacts.models import Contact
from django.db.models import Count

from django.views.decorators.csrf import csrf_exempt
import json
from communication.models import SentimentAnalysis
from django.views.decorators.http import require_http_methods

import re
import logging
logger = logging.getLogger('simplecrm')
class InteractionListAPIView(APIView):
    serializer_class = InteractionSerializer

    def get_queryset(self):
        entity_type = self.request.query_params.get('entity_type')
        entity_id = self.request.query_params.get('entity_id')
        queryset = Interaction.objects.all()

        if entity_type and entity_id:
            try:
                content_type = ContentType.objects.get(model__iexact=entity_type)
                queryset = queryset.filter(entity_type=content_type, entity_id=entity_id)
            except ContentType.DoesNotExist:
                return Interaction.objects.none()  # No results if the content type does not exist

        return queryset

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        try:
            entity_type = request.data.get('entity_type')
            entity_id = request.data.get('entity_id')
            interaction_type = request.data.get('interaction_type')
            tenant_id = request.data.get('tenant_id')
            notes = request.data.get('notes')

            # Get the ContentType object for the specified entity type (case insensitive)
            content_type = ContentType.objects.get(model__iexact=entity_type)
            tenant = get_object_or_404(Tenant, id=tenant_id)
            # Retrieve the entity instance based on entity_id
            entity_instance = content_type.get_object_for_this_type(id=entity_id)

            # Create the Interaction instance
            interaction = Interaction.objects.create(
                entity_type=content_type,
                entity_id=entity_instance.id,
                interaction_type=interaction_type,
                interaction_datetime=datetime.now(),
                notes=notes,
                tenant=tenant
            )

            serializer = self.serializer_class(interaction)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except ContentType.DoesNotExist:
            return Response({'error': f"ContentType matching query does not exist for entity type: {entity_type}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'An error occurred while processing the request: {e}'}, status=status.HTTP_400_BAD_REQUEST)
        
def extract_cltv(request, entity_type_id):
    try:
        interactions = Interaction.objects.filter(entity_type_id=entity_type_id)

        report_data = []

        # Iterate over interactions
        for interaction in interactions:
            # Parse notes field to extract amount and contact information
            notes = interaction.notes
            contact = None
            amount = None

            if notes:
                # Use regular expressions to extract contact and amount
                contact_match = re.search(r'Contact: (\w+)', notes)
                amount_match = re.search(r'amount: (\d+)', notes)

                if contact_match:
                    contact = contact_match.group(1)
                if amount_match:
                    amount = amount_match.group(1)

            # Construct report entry
            report_entry = {
                'interaction_type': interaction.interaction_type,
                'interaction_datetime': interaction.interaction_datetime,
                'contact': contact,
                'amount': amount
            }

            # Add report entry to report data list
            report_data.append(report_entry)

            response_data = {'total_interaction':interactions.count(), 'interaction':report_data}

        # Return report data as JSON response
        return JsonResponse(response_data, safe=False)
    except Exception as e:
        # Handle exceptions
        return JsonResponse({'error': str(e)}, status=500)
class InteractionDetailAPIView(APIView):
    serializer_class = InteractionSerializer

    def get(self, request, pk, *args, **kwargs):
        interaction = get_object_or_404(Interaction, pk=pk)
        serializer = self.serializer_class(interaction)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class RetrieveInteractionsView(APIView):
    def get(self, request, entity_type, entity_id=None, *args, **kwargs):
        try:
            content_type = ContentType.objects.get(id=entity_type)
            if entity_id:
                interactions = Interaction.objects.filter(entity_type=content_type, entity_id=entity_id)
            else:
                interactions = Interaction.objects.filter(entity_type=content_type, entity_id__isnull=True)

            interactions_data = [{'id':inter.id,'interaction_type': inter.interaction_type, 'datetime':inter.interaction_datetime} for inter in interactions]

            return Response({'success': True, 'interactions': interactions_data}, status=status.HTTP_200_OK)
        except ContentType.DoesNotExist:
            return Response({'success': False, 'message': 'Invalid entity_type'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'success': False, 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class callsListAPIView(generics.ListCreateAPIView):
    queryset = Calls.objects.all()  # Using call model queryset instead of Lead
    serializer_class = callsSerializer  # Using callSerializer instead of LeadSerializer
    # permission_classes = (IsAdminUser,)  # Optionally, uncomment and modify the permission classes

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            print(f"An error occurred while processing the request: {e}")
            raise  # Re-raise the exception for Django to handle

class callsDetailAPIView(RetrieveUpdateDestroyAPIView):
    queryset = Calls.objects.all()
    serializer_class = callsSerializer
    # Uncomment the line below to restrict access to admin users only
    # permission_classes = (IsAdminUser,)

class MeetingListCreateAPIView(ListCreateAPIView):
    queryset = Meetings.objects.all()
    serializer_class = meetingsSerializer

class MeetingDetailAPIView(RetrieveUpdateDestroyAPIView):
    queryset = Meetings.objects.all()
    serializer_class = meetingsSerializer


@csrf_exempt
def save_conversations(request, contact_id):
    try:
        if request.method == 'POST':
            source = request.GET.get('source', '')
            body = json.loads(request.body)
            conversations = body.get('conversations', [])
            tenant = body.get('tenant')
            bpid = body.get('business_phone_number_id')
            

            for message in conversations:
                text = message.get('text', '')
                sender = message.get('sender', '')

                # Create and save Conversation object
                Conversation.objects.create(contact_id=contact_id, message_text=text, sender=sender,tenant_id=tenant,source=source, business_phone_number_id = bpid)

            print("Conversation data saved successfully!")
            return JsonResponse({"message": "Conversation data saved successfully!"}, status=200)

        return JsonResponse({"error": "Invalid request method"}, status=400)

    except Exception as e:
        print("Error while saving conversation data:", e)
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def view_conversation(request, contact_id):
    try:
        # Query conversations for a specific contact_id
        source = request.GET.get('source', '')
        bpid = request.GET.get('bpid')
        tenant = request.headers.get('X-Tenant-Id')
        conversations = Conversation.objects.filter(contact_id=contact_id,business_phone_number_id=bpid,source=source).values('message_text', 'sender').order_by('date_time')
        # Format data as per your requirement
        formatted_conversations = []
        for conv in conversations:
            formatted_conversations.append({'text': conv['message_text'], 'sender': conv['sender']})
        
        #for sentiment
        contact = Contact.objects.get(phone=contact_id, tenant_id = tenant)
        if contact:
            print(contact)
            contactID = contact.id
            sentiment = SentimentAnalysis.objects.filter(contact_id_id = contactID).order_by('timestamp').first()
            if sentiment:
                dominant_emotion = sentiment.dominant_emotion
                print("dominant emotion found: ", dominant_emotion)
                formatted_conversations.append({'dominant_emotion': dominant_emotion})
            else:
                dominant_emotion = None
                print("No dominant emotion found for contact id: ", contact_id)
        
        return JsonResponse(formatted_conversations, safe=False)

    except Exception as e:
        print("Error while fetching conversation data:", e)
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def get_unique_instagram_contact_ids(request):
    try:
        unique_contact_ids = Conversation.objects.filter(source='instagram').values_list('contact_id', flat=True).distinct()
        return JsonResponse({"unique_contact_ids": list(unique_contact_ids)})
    except Exception as e:
        print("Error while fetching unique contact IDs:", e)
        return JsonResponse({"error": "Error while fetching unique contact IDs"}, status=500)
    
class EmailListAPIView(generics.ListCreateAPIView):
    serializer_class = EmailSerializer

    def get_queryset(self):
        queryset = Email.objects.all()
        email_type = self.request.query_params.get('email_type', None)
        if email_type:
            queryset = queryset.filter(email_type=email_type)
        return queryset

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"An error occurred while processing the request: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
class EmailDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Email.objects.all()
    serializer_class = EmailSerializer

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer

    def list(self, request):
        """
        Handle GET requests to retrieve all Group entries.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """
        Handle GET requests to retrieve a single Group entry by ID.
        """
        group = self.get_object()
        serializer = self.get_serializer(group)
        return Response(serializer.data)

    def create(self, request):
        """
        Handle POST requests to create a new Group entry.
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        """
        Handle PUT requests to update a Group entry by ID.
        """
        group = self.get_object()
        serializer = self.get_serializer(group, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        """
        Handle DELETE requests to delete a Group entry by ID.
        """
        group = self.get_object()
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
def save_whatsapp_conversations_to_messages(request):
    # Fetch all interaction conversations (or apply any filter if needed)
    conversations = Conversation.objects.filter(mapped=False)


    if not conversations:
        return Response({"message": "No WhatsApp conversations found."}, status=status.HTTP_404_NOT_FOUND)

    for conversation in conversations:
        # Check if the content is empty
        if not conversation.message_text:
            print(f"Conversation {conversation.id} is empty and skipped.")
            continue  # Skip to the next conversation if the content is empty
        # Prepare the message data
        message_data = {
            'sender': 3,
            'content': conversation.message_text,
            'sent_at': datetime.now(),  # Or use a field from the conversation if available
            'platform': 'whatsapp',  # Adjust as needed
            'userid': conversation.contact_id  # Adjust based on your model
        }

        # Serialize and save the data
        serializer = MessageSerializer(data=message_data)
        if serializer.is_valid():
            serializer.save()
            conversation.mapped = True
            conversation.save()
             # Print confirmation message to the console
            print(f"Conversation {conversation.id} saved to messages.") 
        else:
            # Return an error if serialization fails
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"message": "WhatsApp conversations saved to messages successfully."}, status=status.HTTP_201_CREATED)


class GroupInteractionMessageView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        try:
            tenant_id = request.headers.get('X-Tenant-Id')  # Extract tenant ID from headers
            if not tenant_id:
                return Response({"error": "Missing X-Tenant-Id header."}, status=status.HTTP_400_BAD_REQUEST)
            
            group_interaction_messages_into_conversations(tenant_id)  # Call the function to group messages
            return Response({"message": "Messages grouped into conversations successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

from datetime import timedelta
from .models import  Conversation
from contacts.models import Contact
from django.utils import timezone

def group_interaction_messages_into_conversations(tenant_id):
    try:
        # Fetch only messages that haven't been mapped, ordered by sent_at
        messages = Conversation.objects.filter(mapped=False).order_by('sent_at')
        print(f"Total unmapped messages fetched: {messages.count()}")  # Log the number of fetched messages

        if messages.count() == 0:
            print("No unmapped messages found.")

        # Group messages by user and platform
        grouped_messages = {}
        for message in messages:
            key = (message.contact_id, message.source)
            if key not in grouped_messages:
                grouped_messages[key] = []
            grouped_messages[key].append(message)

        print(f"Total groups created: {len(grouped_messages)}")  # Log the number of groups

        # Now process the grouped messages to create conversations
        for (contact_id, source), message_group in grouped_messages.items():
            print(f"Processing group for UserID={contact_id}, Platform={source}, Message count: {len(message_group)}")
            current_conversation = []

            # Sort the messages by sent_at
            message_group.sort(key=lambda x: x.sent_at)

            for message in message_group:
                if not current_conversation:
                    current_conversation.append(message)
                else:
                    last_message_time = current_conversation[-1].sent_at
                    # Set a time threshold (e.g., 20 minutes)
                    if message.sent_at - last_message_time <= timedelta(minutes=20):
                        current_conversation.append(message)
                    else:
                        # Save the current conversation to the database
                        save_interaction_conversation(current_conversation, contact_id, source, tenant_id)
                        current_conversation = [message]

            if current_conversation:
                save_interaction_conversation(current_conversation, contact_id,source, tenant_id)

            # After saving conversations, mark these messages as mapped
            for msg in current_conversation:
                msg.mapped = True
                msg.save()
                print(f"Marked message as mapped: {msg.id}")

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        
def save_interaction_conversation(message_group, contact_id, source, tenant_id):
    try:

        contact = Contact.objects.get(phone=contact_id, tenant_id=tenant_id)

        # Combine messages into a single string
        combined_messages = "\n".join([f"{message.sent_at}: {message.content}" for message in message_group])

        # Create a unique conversation_id
        conversation_id = f"{contact_id}_{source}_{timezone.now().timestamp()}"

        # Create a new Conversation object
        new_conversation = Conversation.objects.create(
            user=message_group[0].sender,  # Set the user (or change as necessary)
            conversation_id=conversation_id,
            messages=combined_messages,  # Store the combined messages
            platform=source,
            contact_id=contact
        )
        
        print(f"Conversation saved: ID={new_conversation.id}, UserID={contact_id}, Platform={source}")
    
    except Contact.DoesNotExist:
        print(f"Contact not found for UserID={source}, TenantID={tenant_id}")
    
    except Exception as e:
        print(f"Error while saving conversation: {str(e)}")